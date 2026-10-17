# Changelog

## Unreleased

`csv` operations `welch_t` and `welch_p`: Welch's t statistic and its p-value (two-sided, or one-sided with `tails: 1`) for two groups of a column, using only the standard library. Tested against the closed forms for 1 and 2 degrees of freedom and published table values.
A `trend` check type: tests that totals over ordered periods are rising, falling, or peak or trough at a named period, and shows the totals.
Limits section no longer says t-tests cannot be checked.
- The report has a `coverage` block (checks decided and undecided, reasons, and a note that claims without a check are not counted), a one-line summary on stderr, and the same line in the HTML report.
- `--min-coverage PCT`: exit 3 when fewer than PCT percent of checks were decided and nothing else failed.
- `csv` checks accept `filter` (`equals`, `not_equals`, `in`, `gt`, `gte`, `lt`, `lte`; one condition or a list), so group means, sums and counts can be checked.
- New `csv` operations: `share` (percentage of rows passing `filter` out of those passing `within`, text columns allowed), `pearson` and `slope` (with `column2`).
- A check whose data cannot be used now yields an `ERROR` finding for that check, and the other checks still run. Before, the first such check stopped the whole run with exit 2. Malformed checks files still exit 2.

## 0.1.0

First release.

- Recalculates percentages, sums, means, medians, counts, minimums, maximums, differences, ratios and percentage changes from supplied values.
- Reads CSV columns directly, so a reported total can be checked against the file.
- Compares at the precision the report used (`decimals`) instead of a fixed tolerance.
