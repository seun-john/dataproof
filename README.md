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

Each check gives `PASS` or `MISMATCH`, with the reported value, the recomputed value, their difference, the tolerance used, your `label` and `lineage` notes.

| `type` | Inputs | Recomputes |
| --- | --- | --- |
| `percentage` | `numerator`, `denominator` | 100 x numerator / denominator (needs 0 <= numerator <= denominator, denominator > 0) |
| `ratio` | `numerator`, `denominator` | numerator / denominator |
| `difference` | `a`, `b` | a - b |
| `percent_change` | `old`, `new` | (new - old) / abs(old) x 100 |
| `sum`, `mean`, `median`, `count`, `min`, `max` | `values` (non-empty) | the statistic |
| `csv` | `path`, `column`, `op` (any statistic above) | the statistic over a CSV column; blanks are skipped and counted in `rows_used`, `1,200` is read as 1200 |
| `match` | `source_value` | compares with a single source value |

**Precision.** Say how the report rounded with `"decimals": 1` and DataProof allows half a unit in the last place, so `66.7` matches 2/3 as a percentage and `66.6` does not. Without `decimals`, an absolute `tolerance` applies (default 0.05).

CSV paths must be inside `--root`; anything that escapes it is refused. Files over 20 MiB are refused. Non-numeric cells stop the check with the line number.

All commands take `-o report.json`, `--html report.html` and `--strict`. Exit codes: 0 completed, 1 `--strict` and a mismatch (or no checks) was reported, 2 unusable input.

## Limits

- DataProof recomputes. It cannot tell whether the right quantity was reported, whether a denominator was appropriate, or whether a statistical test was valid.
- Only JSON and CSV inputs. There is no XLSX or SPSS import, no formula comparison and no chart checking.
- Floating-point arithmetic is used, which is why a tolerance or `decimals` is always applied.

## Develop

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
```

MIT licence.
