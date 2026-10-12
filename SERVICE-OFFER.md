# CSV audit and cleanup — USD150

Turn one messy CSV into a reviewable data file with a clear record of every change.

**Fixed scope:** one UTF-8, comma-delimited CSV with a header and up to 10,000 data records. Before work begins, we agree which whitespace rules to apply, whether to reject blank records, and whether to remove exact or normalized duplicates. Column order is preserved. Empty values remain empty; no facts or missing values are invented.

**You receive:** the cleaned CSV, an excluded-record file with reasons and original record text, a cell-level change log, a JSON audit with row counts and source-file SHA-256, and the reusable Python script with run instructions. Records with the wrong number of columns are preserved in the exclusion audit. Broken quoting or ambiguous headers are reported for clarification before cleanup proceeds.

**Indicative price:** USD150 for this scope, confirmed after reviewing your sample and cleanup rules. **Estimated delivery:** one business day after the file, rules, scope and payment terms are agreed. Final platform fees, payout charges and currency conversion depend on the checkout and payout method.

**Outside this scope:** spreadsheet workbooks, database integrations, data enrichment, filling missing values and manual reconstruction of malformed files.

The original synthetic portfolio demo shows the cleanup outputs and reproducible local checks.

**Discuss your file:** [open a GitHub issue](https://github.com/reacx-research/csv-audit-demo/issues/new) with its approximate size, intended columns and desired cleanup rules. Do not post actual client data or sensitive samples in a public issue. Share the file or representative sample through an agreed private channel.
