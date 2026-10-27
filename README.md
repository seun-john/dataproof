<p align="center">
  <img src="assets/logo.png" alt="DataProof logo" width="420">
</p>

# DataProof

Recalculate the numbers in a report from the data behind them.

AI-written tables and summaries often contain totals that do not add up, percentages with the wrong denominator and means that nobody computed. DataProof recomputes each number from the values you give it, or from a CSV column, and shows the difference. It uses only the Python standard library and makes no network requests.

## Install

Requires Python 3.10 or newer.

```bash
pip install git+https://github.com/seun-john/dataproof.git
```

## Use

```bash
dataproof check checks.json --root . -o report.json --html report.html --strict
```

```json
{"checks": [
  {"type": "percentage", "numerator": 45, "denominator": 60, "reported": 75, "label": "Pass rate"},
  {"type": "mean", "values": [2, 4, 9], "reported": 5.0, "decimals": 1},
  {"type": "csv", "path": "survey.csv", "column": "age", "op": "mean", "reported": 34.2, "decimals": 1,
   "lineage": ["survey.csv, column age"]}
]}
```

Each check gives `PASS`, `MISMATCH` or, when its data cannot be used, `ERROR`, with the reported value, the recomputed value, their difference, the tolerance used, your `label` and `lineage` notes.

| `type` | Inputs | Recomputes |
| --- | --- | --- |
| `percentage` | `numerator`, `denominator` | 100 x numerator / denominator (needs 0 <= numerator <= denominator, denominator > 0) |
| `ratio` | `numerator`, `denominator` | numerator / denominator |
| `difference` | `a`, `b` | a - b |
| `percent_change` | `old`, `new` | (new - old) / abs(old) x 100 |
| `sum`, `mean`, `median`, `count`, `min`, `max` | `values` (non-empty) | the statistic |
| `csv` | `path`, `column`, `op` (any statistic above) | the statistic over a CSV column; blanks are skipped and counted in `rows_used`, `1,200` is read as 1200 |
| `match` | `source_value` | compares with a single source value |

**Groups and relationships in a CSV.** A `csv` check can be limited to some rows with `filter`, and has three more operations:

```json
{"type": "csv", "path": "trips.csv", "column": "duration_min", "op": "mean", "reported": 13.0, "decimals": 1,
 "filter": {"column": "station", "equals": "Campus"}}
{"type": "csv", "path": "trips.csv", "column": "member_trip", "op": "share", "reported": 54.5, "decimals": 1,
 "filter": {"column": "member_trip", "equals": "Yes"}, "within": {"column": "station", "equals": "Campus"}}
{"type": "csv", "path": "orders.csv", "column": "order_value", "column2": "delivery_days", "op": "slope",
 "reported": -17.52, "decimals": 2}
```

- `filter` is one condition or a list (all must hold). A condition names a `column` and exactly one of `equals`, `not_equals`, `in` (a list), `gt`, `gte`, `lt`, `lte`. Text is compared after trimming; the numeric tests read `1,200` as 1200 and treat blank or non-numeric cells as not matching.
- `share` is the percentage of rows that pass `filter`, out of the rows that pass `within` (default: all rows). Only rows with something in `column` count, and `column` may be text.
- `pearson` is the correlation of `column` and `column2`; `slope` is the least-squares slope of `column` (y) on `column2` (x). Only rows with a number in both are used, after the filter, and at least 3 are needed.

**Two groups and period patterns.** Two more operations compare groups and test a described pattern:

```json
{"type": "csv", "path": "d.csv", "column": "yield", "group_column": "field", "groups": ["Mill Field", "Long Acre"], "op": "welch_t", "reported": 6.07, "decimals": 2}
{"type": "csv", "path": "d.csv", "column": "yield", "group_column": "field", "groups": ["Mill Field", "Long Acre"], "op": "welch_p", "reported": 0.509, "decimals": 3}
{"type": "trend", "path": "d.csv", "column": "charge_usd", "period_column": "quarter", "periods": ["Q1", "Q2", "Q3"], "pattern": "falling"}
```

- `welch_t` is Welch's t for mean(first group) minus mean(second group), so the order of `groups` sets the sign. `welch_p` is its p-value from Student's t with the Welch-Satterthwaite degrees of freedom, computed with the standard library (an incomplete beta function). It is two-sided unless you give `"tails": 1`, which halves it. Each group needs at least 2 numbers. A claim that gives both t and p needs one check for each; the evidence shows the group sizes and the degrees of freedom.
- `trend` has no `reported` number. It adds up `column` for each of the `periods` (or averages with `"agg": "mean"`) and passes when `pattern` holds: `rising` or `falling` (every step strictly up or down, in the order listed), or `peak` / `trough` (the period named in `at`, among at least three periods, is strictly higher or lower than all the others). The totals are in the evidence. A tie is not a rise.

If the data a check points at cannot be used (file or column missing, a non-numeric cell, a filter that matches no rows, a constant column), that check gets an `ERROR` finding with the reason and the others still run. Under `--strict`, `ERROR` counts like a mismatch (exit 1). A malformed checks file (unknown type or operation, a missing field, a bad filter) still stops the run with exit 2.

**Precision.** Say how the report rounded with `"decimals": 1` and DataProof allows half a unit in the last place, so `66.7` matches 2/3 as a percentage and `66.6` does not. Without `decimals`, an absolute `tolerance` applies (default 0.05).

CSV paths must be inside `--root`; anything that escapes it is refused. Files over 20 MiB are refused. Non-numeric cells stop the check with the line number.

All commands take `-o report.json`, `--html report.html` and `--strict`. Exit codes: 0 completed, 1 `--strict` and a mismatch (or no checks) was reported, 2 unusable input, 3 `--min-coverage` was not met.

**Coverage.** The report has a `coverage` object, and a line on stderr: `coverage: decided 8 of 10 checks; 2 could not be checked (data_unusable 2)`. A check is decided when it came out `PASS` or `MISMATCH`; it is undecided when its data could not be used (`ERROR`, reason `data_unusable`). Claims that nobody wrote a check for are not counted, because DataProof cannot see them; the report says so in `notes`. `--min-coverage PCT` exits 3 when fewer than PCT percent of the checks were decided and nothing else failed; `--strict` mismatches still exit 1.

## Limits

- DataProof recomputes. It cannot tell whether the right quantity was reported, whether a denominator was appropriate, or whether a statistical test was valid.
- The only tests are Welch's t and its p-value. There is no check for other tests (paired, Mann-Whitney, chi-squared), for confidence intervals, or for regression coefficients other than the simple slope.
- Only JSON and CSV inputs. There is no XLSX or SPSS import, no formula comparison and no chart checking.
- Floating-point arithmetic is used, which is why a tolerance or `decimals` is always applied.

## Develop

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
```

MIT licence.


## Research paper

This tool was evaluated, with and without each tool, in an open preprint: Oluwawalemi, O. J. (2026). Do Verification Tools Improve on an AI Reader? A With-and-Without Evaluation of Fifteen Open-Source Tools for AI-Assisted Research. Zenodo. https://doi.org/10.5281/zenodo.23404947

The test corpora, truth labels, verdicts and scripts are in the same Zenodo record. Independent replication and testing are welcome. Please open an issue to share results.
