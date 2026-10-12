# Portfolio case: CSV audit and cleanup

**Original synthetic demonstration by Reacx Research, 12 October 2026.** This is a working local tool and example, not a customer project, purchased order or earned income. Results verified by reproducible local checks. No client deployment is claimed.

A small fictional product sheet combines leading/trailing spaces, a duplicate written with different spacing, a blank record, a missing quantity, a short row, an extra-column row, a quoted comma, embedded quotes, a quoted multiline note, Unicode text and a UTF-8 BOM. The CLI separates structural errors from approved cleanup and keeps every source record accounted for.

## Measured result

| Run | Input data records | Retained | Excluded with audit | Changed cells |
|---|---:|---:|---:|---:|
| Default audit | 8 | 6 | 2 | 0 |
| Approved trim + reject blank records + normalized dedupe | 8 | 4 | 4 | 2 |

Both runs preserve the four columns in this order: `record_id`, `item`, `quantity`, `note`. The quantity for `S-003` stays blank. The multiline note, quoted comma, embedded quotes, Unicode and BOM survive. The normalized duplicate comparison is case-sensitive and keeps the first occurrence.

The original `fixtures/messy.csv` SHA-256 is:

```text
c310516030d396301a3ae221eadb721a7083f6fbe42541f4090e11b1696e9942
```

The hash is identical after both deliveries. Input records reconcile exactly: 6 + 2 = 8 in default mode; 4 + 4 = 8 after approved cleanup.

## Concrete before and after

| Field or record | Original | Approved result |
|---|---|---|
| First row, `item` | ` Café mug ` | `Café mug`; cell edit logged |
| First row, `quantity` | ` 2 ` | `2`; cell edit logged |
| Data row 3 | ` S-001 ,Café mug,2,"Gift, blue"` | Audited as duplicate of data row 1 |
| Data row 4, quantity | Empty | Empty |
| Data row 5 | Empty physical line | Audited as an explicitly rejected blank record |
| Data row 6 | `S-004,Sticker` | Audited as two fields instead of four; no invented quantity/note |
| Data row 7 | `S-005,Card,1,OK,EXTRA` | Audited as five fields instead of four; extra value retained in audit |

`fixtures/cleanup/cleaned.csv` contains:

```csv
record_id,item,quantity,note
S-001,Café mug,2,"Gift, blue"
S-002,Notebook,3,"Two lines:
keep both"
S-003,Pen,,Quantity missing: retain blank
S-006,"Quote ""inside""",1,Contains Zoë and 東京
```

The file also preserves the source BOM. This fenced preview omits the invisible BOM marker for readability.

## Reviewable artifacts

- `csv_audit.py`: reusable Python 3.9+ standard-library CLI.
- `fixtures/messy.csv`: original fictional source, retained without edits.
- `fixtures/default/`: no intentional cell edits; width failures audited.
- `fixtures/cleanup/`: approved sample cleanup, with `cleaned.csv`, `audit.json`, `rejected.csv` and `changes.csv`.
- `tests/test_csv_audit.py`: 22 meaningful test methods, including all 18 rule combinations and the 10,000-record boundary.
- `check.py`: independent fixture regeneration, artifact comparison and claim verification.
- `README.md`: usage, rules, safety/encoding boundaries and exit codes.
- `SERVICE-OFFER.md`: indicative USD150 service proposal, subject to scope agreement, for one file of up to 10,000 records, estimated one business day after data and scope approval.

Actual tests ran locally under Python 3.9.6. The implementation uses only Python 3.9-supported syntax and standard-library APIs. No real vendor contacts, client data, authenticated services or network APIs were involved.

This is a new original demo, not a paid client job. USD150 is an indicative proposal after scope agreement, not a binding contract. Final fees, payout costs and currency conversion depend on the actual checkout and payout route; no net EUR amount is promised. Publishing this demonstration does not mean the service has sold.
