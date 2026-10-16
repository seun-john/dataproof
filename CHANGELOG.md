# Changelog

## Unreleased

- `csv` checks accept `filter` (`equals`, `not_equals`, `in`, `gt`, `gte`, `lt`, `lte`; one condition or a list), so group means, sums and counts can be checked.
- New `csv` operations: `share` (percentage of rows passing `filter` out of those passing `within`, text columns allowed), `pearson` and `slope` (with `column2`).
- A check whose data cannot be used now yields an `ERROR` finding for that check, and the other checks still run. Before, the first such check stopped the whole run with exit 2. Malformed checks files still exit 2.

## 0.1.0

First release.

- Recalculates percentages, sums, means, medians, counts, minimums, maximums, differences, ratios and percentage changes from supplied values.
- Reads CSV columns directly, so a reported total can be checked against the file.
- Compares at the precision the report used (`decimals`) instead of a fixed tolerance.
