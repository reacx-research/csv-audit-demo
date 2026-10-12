"""Rebuild and verify the original synthetic portfolio case without network use."""
import ast
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("csv_audit", ROOT / "csv_audit.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
fixture = ROOT / "fixtures/messy.csv"
before = fixture.read_bytes()
expected_sha = "c310516030d396301a3ae221eadb721a7083f6fbe42541f4090e11b1696e9942"
assert hashlib.sha256(before).hexdigest() == expected_sha
checks = []
policies = [("default", {}, (8, 6, 2, 0)),
            ("cleanup", {"whitespace": "trim", "blank_rows": "reject", "dedupe": "normalized"},
             (8, 4, 4, 2))]
with tempfile.TemporaryDirectory() as temp:
    for name, options, expected in policies:
        output = Path(temp) / name
        audit = tool.run(fixture, output, **options)
        counts = tuple(audit[k] for k in ["input_data_records", "retained_data_records",
                                         "rejected_data_records", "changed_cells"])
        assert counts == expected, (name, counts)
        assert audit["input_data_records"] == audit["retained_data_records"] + audit["rejected_data_records"]
        assert audit["input_sha256"] == audit["input_sha256_after"] == expected_sha
        assert audit["input_unchanged"] is True
        assert audit["columns"] == ["record_id", "item", "quantity", "note"]
        assert audit["utf8_bom_preserved"] is True
        for file in ["cleaned.csv", "audit.json", "rejected.csv", "changes.csv"]:
            assert (output / file).read_bytes() == (ROOT / "fixtures" / name / file).read_bytes(), (name, file)
            checks.append(name + "/" + file + " byte-identical regeneration")
        with (output / "cleaned.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        assert next(r for r in rows if r and r[0] == "S-003")[2] == ""
        assert next(r for r in rows if r and r[0] == "S-002")[3] == "Two lines:\r\nkeep both"
        assert next(r for r in rows if r and r[0] == "S-006")[1] == 'Quote "inside"'
        checks.append(name + " text/column/BOM/missing-value preservation")
assert fixture.read_bytes() == before

test_tree = ast.parse((ROOT / "tests/test_csv_audit.py").read_text())
methods = [node.name for node in ast.walk(test_tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
assert len(methods) == 22
report = (ROOT / "REPORTportfolio.md").read_text()
for phrase in [expected_sha, "22 meaningful test methods", "one business day", "8 | 6 | 2 | 0", "8 | 4 | 4 | 2", "not a customer project"]:
    assert phrase in report, phrase
offer = (ROOT / "SERVICE-OFFER.md").read_text()
for phrase in ["USD150", "10,000", "one business day", "synthetic portfolio demo", "agreed private channel"]:
    assert phrase in offer, phrase
for file in ["README.md", "SERVICE-OFFER.md", "REPORTportfolio.md"]:
    assert not __import__("re").search(r"\b(?:TODO|TBD|FIXME)\b", (ROOT / file).read_text())
checks.append("Measured portfolio claims,22 test methods,original source hash and honest offer")
result = {"python": sys.version.split()[0], "source_sha256": expected_sha,
          "input_unchanged": True, "fixture_runs": 2, "reproduced_artifacts": 8,
          "test_methods": len(methods), "policy_matrix_combinations": 18,
          "checks": checks, "client_engagements": 0, "earned_eur": 0}
(ROOT / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
print("CHECK PASS: 2 fixture runs;8 artifact comparisons;22 test methods; original bytes unchanged; EUR0 earned")
