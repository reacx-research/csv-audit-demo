#!/usr/bin/env python3
"""Auditable UTF-8 CSV cleanup. Python 3.9+, standard library only."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import unicodedata


class AuditError(ValueError):
    """An input or destination cannot safely be processed."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def normalize(value, mode):
    if mode == "trim":
        return value.strip()
    if mode == "collapse":
        return " ".join(value.split())
    return value


def inspect_csv(data, whitespace="preserve", blank_rows="keep", dedupe="none",
                max_rows=10000):
    """Return an in-memory result; never change source bytes or infer values.

    Physical empty lines are valid blank records. Other records must match the
    header width. Malformed quoting is fatal: record boundaries are unknowable.
    """
    if whitespace not in {"preserve", "trim", "collapse"}:
        raise AuditError("Unknown whitespace mode")
    if blank_rows not in {"keep", "reject"} or dedupe not in {"none", "exact", "normalized"}:
        raise AuditError("Unknown blank-row or deduplication mode")
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 1:
        raise AuditError("max_rows must be a positive integer")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AuditError("Input must be UTF-8; no encoding conversion was guessed") from exc
    # Unicode paragraph separators are cell content, not CSV record boundaries.
    physical = io.StringIO(text, newline="").readlines()
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise AuditError("CSV is empty: a header is required") from exc
    except csv.Error as exc:
        raise AuditError("Malformed CSV header: " + str(exc)) from exc
    if not header or any(not name.strip() for name in header):
        raise AuditError("Header names must be nonblank")
    if len(set(header)) != len(header):
        raise AuditError("Duplicate header names are ambiguous")

    rows, rejected, changes, seen = [], [], [], {}
    previous_line, input_rows = reader.line_num, 0
    while True:
        start_line = previous_line + 1
        try:
            original = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise AuditError("Malformed CSV at physical line %d: %s; no outputs written"
                             % (reader.line_num, exc)) from exc
        end_line = reader.line_num
        previous_line = end_line
        input_rows += 1
        if input_rows > max_rows:
            raise AuditError("Input exceeds the %d-data-record limit; no outputs written" % max_rows)
        record = {
            "row_number": input_rows,
            "line_from": start_line,
            "line_to": end_line,
            "raw_record": "".join(physical[start_line - 1:end_line]),
            "values": original,
        }
        is_blank = not original or all(not value.strip() for value in original)
        if original and len(original) != len(header):
            record["reason"] = "column_count"
            record["detail"] = "Expected %d columns, found %d" % (len(header), len(original))
            rejected.append(record)
            continue
        if is_blank and blank_rows == "reject":
            record["reason"] = "blank_row"
            record["detail"] = "Blank-row rejection explicitly enabled"
            rejected.append(record)
            continue
        cleaned = [normalize(value, whitespace) for value in original]
        if dedupe != "none":
            key = tuple(cleaned)
            if dedupe == "normalized":
                # Case-sensitive: product codes and names must not be conflated.
                key = tuple(unicodedata.normalize("NFC", value.strip()) for value in cleaned)
            if key in seen:
                record["reason"] = "duplicate_row"
                record["detail"] = "Matches retained data row %d using %s comparison" % (seen[key], dedupe)
                record["duplicate_of"] = seen[key]
                rejected.append(record)
                continue
            seen[key] = input_rows
        for index, (old, new) in enumerate(zip(original, cleaned)):
            if old != new:
                changes.append({"row_number": input_rows, "line_from": start_line,
                                "line_to": end_line, "column_index": index + 1,
                                "column_name": header[index], "old_value": old,
                                "new_value": new, "operation": whitespace})
        rows.append(cleaned)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    output = buffer.getvalue().encode("utf-8")
    has_bom = data.startswith(b"\xef\xbb\xbf")
    if has_bom:
        output = b"\xef\xbb\xbf" + output
    audit = {
        "schema_version": 1,
        "input_sha256": sha256(data), "input_bytes": len(data),
        "output_sha256": sha256(output), "utf8_bom_preserved": has_bom,
        "columns": header, "input_data_records": input_rows,
        "retained_data_records": len(rows), "rejected_data_records": len(rejected),
        "changed_cells": len(changes),
        "options": {"whitespace": whitespace, "blank_rows": blank_rows,
                    "dedupe": dedupe, "max_rows": max_rows},
        "rejected": rejected,
        "notes": ["No missing values inferred; fields remain text.",
                  "Header names and column order unchanged.",
                  "Output serialization uses LF; quoting may differ from input.",
                  "Original file is preserved byte for byte.",
                  "Normalized dedupe uses NFC and edge trimming, case-sensitive."],
    }
    return {"cleaned": output, "audit": audit, "changes": changes}


def table_bytes(fieldnames, records):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue().encode("utf-8")


def same_file(left, right):
    if left.resolve() == right.resolve():
        return True
    return left.exists() and right.exists() and os.path.samefile(left, right)


def run(input_path, output_dir, **options):
    input_path, output_dir = Path(input_path), Path(output_dir)
    names = ["cleaned.csv", "audit.json", "rejected.csv", "changes.csv"]
    destinations = [output_dir / name for name in names]
    for destination in destinations:
        if same_file(input_path, destination):
            raise AuditError("Refusing in-place overwrite of the input (including links)")
        if destination.exists() or destination.is_symlink():
            raise AuditError("Output already exists: %s; choose a fresh directory" % destination)
    original = input_path.read_bytes()
    result = inspect_csv(original, **options)
    result["audit"]["source_name"] = input_path.name
    if input_path.read_bytes() != original:
        raise AuditError("Source changed during processing; no outputs written")
    result["audit"]["input_sha256_after"] = sha256(original)
    result["audit"]["input_unchanged"] = True
    rejection_rows = [{"row_number": r["row_number"], "line_from": r["line_from"],
                       "line_to": r["line_to"], "reason": r["reason"], "detail": r["detail"],
                       "raw_record": r["raw_record"],
                       "parsed_values_json": json.dumps(r["values"], ensure_ascii=False)}
                      for r in result["audit"]["rejected"]]
    artifacts = [result["cleaned"],
                 (json.dumps(result["audit"], ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                 table_bytes(["row_number", "line_from", "line_to", "reason", "detail",
                              "raw_record", "parsed_values_json"], rejection_rows),
                 table_bytes(["row_number", "line_from", "line_to", "column_index",
                              "column_name", "old_value", "new_value", "operation"], result["changes"])]
    output_dir.mkdir(parents=True, exist_ok=True)
    # Exclusive creation refuses overwrite races. On failure remove only files
    # created by this invocation; every artifact is already serialized in memory.
    created = []
    try:
        for destination, data in zip(destinations, artifacts):
            with destination.open("xb") as target:
                created.append(destination)
                target.write(data)
        if input_path.read_bytes() != original:
            raise AuditError("Source changed during delivery; generated files removed")
    except BaseException:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    return result["audit"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 comma-delimited CSV with a header")
    parser.add_argument("output_dir", type=Path, help="Directory without existing output artifact names")
    parser.add_argument("--whitespace", choices=["preserve", "trim", "collapse"], default="preserve")
    parser.add_argument("--blank-rows", choices=["keep", "reject"], default="keep")
    parser.add_argument("--dedupe", choices=["none", "exact", "normalized"], default="none")
    parser.add_argument("--max-rows", type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        audit = run(args.input, args.output_dir, whitespace=args.whitespace,
                    blank_rows=args.blank_rows, dedupe=args.dedupe, max_rows=args.max_rows)
    except (AuditError, OSError) as exc:
        parser.exit(2, "CSV audit error: %s\n" % exc)
    print(json.dumps({key: audit[key] for key in ["input_data_records", "retained_data_records",
                                                "rejected_data_records", "changed_cells",
                                                "input_unchanged", "input_sha256"]}, indent=2))
    # Successful audited delivery; exclusions require explicit attention in automation.
    return 1 if audit["rejected_data_records"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
