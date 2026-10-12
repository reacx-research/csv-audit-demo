import csv
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("csv_audit", ROOT / "csv_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def parsed(data):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))


class ContentTests(unittest.TestCase):
    def test_no_loss_defaults_preserve_values_duplicates_and_blank_records(self):
        raw = b'id,note\r\n01,"  keep spaces  "\r\n01,"  keep spaces  "\r\n\r\n,\r\n'
        result = audit.inspect_csv(raw)
        self.assertEqual(parsed(result["cleaned"]), parsed(raw))
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["audit"]["input_data_records"], 4)
        self.assertEqual(result["audit"]["retained_data_records"], 4)
        self.assertEqual(result["audit"]["rejected"], [])

    def test_quotes_multiline_unicode_bom_and_column_order(self):
        raw = '\ufeffnote,code,name\r\n"Hello, ""reader""\r\n第二行",001,Zoë\r\n'.encode()
        result = audit.inspect_csv(raw)
        self.assertTrue(result["cleaned"].startswith(b"\xef\xbb\xbf"))
        self.assertEqual(parsed(result["cleaned"]), parsed(raw))
        self.assertEqual(result["audit"]["columns"], ["note", "code", "name"])
        self.assertEqual(result["audit"]["input_data_records"], 1)

    def test_ragged_rows_audited_without_padding_or_truncating(self):
        raw = b'id,note\r\n1,valid\r\n2\r\n3,x,extra\r\n4,last\r\n'
        result = audit.inspect_csv(raw)
        self.assertEqual(parsed(result["cleaned"]), [["id", "note"], ["1", "valid"], ["4", "last"]])
        rejected = result["audit"]["rejected"]
        self.assertEqual([r["values"] for r in rejected], [["2"], ["3", "x", "extra"]])
        self.assertEqual([r["raw_record"] for r in rejected], ["2\r\n", "3,x,extra\r\n"])
        self.assertEqual([r["line_from"] for r in rejected], [3, 4])
        self.assertEqual(result["audit"]["input_data_records"], 4)
        self.assertEqual(result["audit"]["rejected_data_records"], 2)

    def test_rejected_multiline_raw_record_has_exact_physical_bounds(self):
        raw = 'a,b\r\n"one\r\ntwo",x,extra\r\nok,z\r\n'.encode()
        r = audit.inspect_csv(raw)["audit"]["rejected"][0]
        self.assertEqual((r["line_from"], r["line_to"]), (2, 3))
        self.assertEqual(r["raw_record"], '"one\r\ntwo",x,extra\r\n')

    def test_unicode_separator_is_not_a_physical_csv_line(self):
        raw = 'a,b\n1,x\u2028y,extra\n2,z\n'.encode()
        r = audit.inspect_csv(raw)["audit"]["rejected"][0]
        self.assertEqual(r["raw_record"], '1,x\u2028y,extra\n')
        self.assertEqual((r["line_from"], r["line_to"]), (2, 2))

    def test_whitespace_trim_logs_only_actual_changes(self):
        raw = 'id,note\n 001 ," café \n line "\n002,unchanged\n'.encode()
        result = audit.inspect_csv(raw, whitespace="trim")
        self.assertEqual(parsed(result["cleaned"])[1], ["001", "café \n line"])
        self.assertEqual(len(result["changes"]), 2)
        self.assertEqual(result["changes"][1]["old_value"], " café \n line ")
        self.assertEqual(result["changes"][1]["new_value"], "café \n line")
        self.assertEqual(result["changes"][0]["column_name"], "id")

    def test_collapse_whitespace_is_explicit_and_preserve_is_default(self):
        raw = b'a,b\n1,"a\t  b\nc"\n'
        self.assertEqual(parsed(audit.inspect_csv(raw)["cleaned"])[1][1], "a\t  b\nc")
        self.assertEqual(parsed(audit.inspect_csv(raw, whitespace="collapse")["cleaned"])[1][1], "a b c")

    def test_normalized_dedupe_is_opt_in_nfc_trim_and_case_sensitive(self):
        raw = 'id,name\n01, café \n01,cafe\u0301\n01,Café\n'.encode()
        self.assertEqual(audit.inspect_csv(raw)["audit"]["retained_data_records"], 3)
        self.assertEqual(audit.inspect_csv(raw, dedupe="exact")["audit"]["retained_data_records"], 3)
        result = audit.inspect_csv(raw, dedupe="normalized")
        self.assertEqual(parsed(result["cleaned"])[1:], [["01", " café "], ["01", "Café"]])
        rejected = result["audit"]["rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["duplicate_of"], 1)
        self.assertEqual(rejected[0]["values"], ["01", "cafe\u0301"])
        self.assertEqual(result["changes"], [])

    def test_exact_dedupe_retains_first_and_reports_original_duplicate(self):
        result = audit.inspect_csv(b'a,b\n1,x\n1,x\n1,y\n', dedupe="exact")
        self.assertEqual(parsed(result["cleaned"])[1:], [["1", "x"], ["1", "y"]])
        self.assertEqual(result["audit"]["rejected"][0]["raw_record"], "1,x\n")

    def test_blank_rejection_explicit_and_bad_width_is_not_hidden(self):
        raw = b'a,b\n\n , \n,,\n1,x\n'
        result = audit.inspect_csv(raw, blank_rows="reject")
        self.assertEqual([r["reason"] for r in result["audit"]["rejected"]], ["blank_row", "blank_row", "column_count"])
        self.assertEqual(parsed(result["cleaned"])[1:], [["1", "x"]])

    def test_header_only_is_a_valid_zero_record_file(self):
        result = audit.inspect_csv(b'id,note\n')
        self.assertEqual(result["audit"]["input_data_records"], 0)
        self.assertEqual(parsed(result["cleaned"]), [["id", "note"]])

    def test_blank_missing_duplicate_and_badly_quoted_headers_are_rejected(self):
        for raw in [b'', b'\n', b'a,\n', b'a,a\n', b'a,   \n', b'"broken,a\n']:
            with self.subTest(raw=raw), self.assertRaises(audit.AuditError):
                audit.inspect_csv(raw)

    def test_malformed_quoting_fails_closed_instead_of_guessing_new_rows(self):
        for raw in [b'a,b\n1,"unfinished\n2,next\n', b'a,b\n1,"closed"junk\n']:
            with self.subTest(raw=raw), self.assertRaisesRegex(audit.AuditError, "Malformed CSV"):
                audit.inspect_csv(raw)

    def test_invalid_encoding_and_row_limit_fail_before_delivery(self):
        with self.assertRaisesRegex(audit.AuditError, "UTF-8"):
            audit.inspect_csv(b'a\n\xff\n')
        with self.assertRaisesRegex(audit.AuditError, "record limit"):
            audit.inspect_csv(b'a\n1\n2\n', max_rows=1)
        for bad in [0, -1, True]:
            with self.subTest(bad=bad), self.assertRaises(audit.AuditError):
                audit.inspect_csv(b'a\n', max_rows=bad)

    def test_service_10000_row_boundary_and_record_conservation(self):
        raw = b'id,value\n' + b'1,unchanged\n' * 10000
        result = audit.inspect_csv(raw)
        self.assertEqual(result["audit"]["retained_data_records"], 10000)
        self.assertEqual(parsed(result["cleaned"]), parsed(raw))
        with self.assertRaisesRegex(audit.AuditError, "10000-data-record limit"):
            audit.inspect_csv(raw + b'2,extra\n')

    def test_policy_matrix_conserves_records_and_changes_only_retained_cells(self):
        raw = b'a,b\n1, x \n1,x\n\n2\n3,y,extra\n'
        for whitespace in ["preserve", "trim", "collapse"]:
            for blanks in ["keep", "reject"]:
                for dedupe in ["none", "exact", "normalized"]:
                    result = audit.inspect_csv(raw, whitespace=whitespace, blank_rows=blanks, dedupe=dedupe)
                    report = result["audit"]
                    with self.subTest(whitespace=whitespace, blanks=blanks, dedupe=dedupe):
                        self.assertEqual(report["input_data_records"], 5)
                        self.assertEqual(report["retained_data_records"] + report["rejected_data_records"], 5)
                        excluded = {r["row_number"] for r in report["rejected"]}
                        self.assertFalse(any(c["row_number"] in excluded for c in result["changes"]))
                        self.assertEqual(len({r["row_number"] for r in report["rejected"]}), len(report["rejected"]))


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.csv"
        self.source.write_bytes(b'id,note\r\n1, x \r\n2\r\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_full_delivery_keeps_input_bytes_and_all_audit_records(self):
        before = self.source.read_bytes()
        report = audit.run(self.source, self.root / "out", whitespace="trim")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(report["input_sha256"], audit.sha256(before))
        self.assertEqual(report["input_sha256_after"], report["input_sha256"])
        saved = json.loads((self.root / "out/audit.json").read_text())
        self.assertEqual(saved, report)
        with (self.root / "out/rejected.csv").open(newline="", encoding="utf-8") as handle:
            rejected = list(csv.DictReader(handle))
        self.assertEqual(rejected[0]["raw_record"], "2\r\n")
        self.assertEqual(json.loads(rejected[0]["parsed_values_json"]), ["2"])
        with (self.root / "out/changes.csv").open(newline="", encoding="utf-8") as handle:
            changes = list(csv.DictReader(handle))
        self.assertEqual((changes[0]["old_value"], changes[0]["new_value"]), (" x ", "x"))

    def test_refuses_same_input_destination(self):
        source = self.root / "cleaned.csv"
        source.write_bytes(b'a\n1\n')
        before = source.read_bytes()
        with self.assertRaisesRegex(audit.AuditError, "in-place"):
            audit.run(source, self.root)
        self.assertEqual(source.read_bytes(), before)

    def test_refuses_symlink_and_hardlink_destination(self):
        for kind in ["symlink", "hardlink"]:
            out = self.root / kind
            out.mkdir()
            target = out / "cleaned.csv"
            if kind == "symlink":
                target.symlink_to(self.source)
            else:
                import os
                os.link(self.source, target)
            before = self.source.read_bytes()
            with self.subTest(kind=kind), self.assertRaisesRegex(audit.AuditError, "in-place"):
                audit.run(self.source, out)
            self.assertEqual(self.source.read_bytes(), before)

    def test_does_not_overwrite_existing_non_input_output(self):
        out = self.root / "out"
        out.mkdir()
        (out / "audit.json").write_text("existing")
        with self.assertRaisesRegex(audit.AuditError, "already exists"):
            audit.run(self.source, out)
        self.assertEqual((out / "audit.json").read_text(), "existing")
        self.assertFalse((out / "cleaned.csv").exists())

    def test_malformed_input_produces_no_partial_files(self):
        self.source.write_bytes(b'a,b\n1,"unfinished\n')
        with self.assertRaises(audit.AuditError):
            audit.run(self.source, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_cli_exit_codes_distinguish_clean_rejected_and_fatal(self):
        for index, (raw, expected) in enumerate([(b'a\n1\n', 0), (b'a,b\n1\n', 1), (b'a,a\n', 2)]):
            self.source.write_bytes(raw)
            result = subprocess.run([sys.executable, str(ROOT / "csv_audit.py"), str(self.source),
                                     str(self.root / ("cli" + str(index)))], capture_output=True, text=True)
            with self.subTest(expected=expected):
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected < 2:
                    self.assertTrue(json.loads(result.stdout)["input_unchanged"])
                else:
                    self.assertIn("CSV audit error", result.stderr)
                    self.assertFalse((self.root / ("cli" + str(index))).exists())


if __name__ == "__main__":
    unittest.main()
