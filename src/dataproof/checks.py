"""Recalculate reported numbers from the data behind them.

DataProof recomputes; it does not decide whether a number is the right thing to report.
Every result keeps the inputs and the recomputed value so rounding and lineage can be
inspected.
"""

from __future__ import annotations

import csv
import statistics
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from .core import InputError, coverage, finding, inside, number, report, require

MAX_CSV_BYTES = 20 * 1024 * 1024
DEFAULT_TOLERANCE = 0.05

AGGREGATES: dict[str, Callable[[list[float]], float]] = {
    "sum": sum,
    "mean": statistics.fmean,
    "median": statistics.median,
    "count": lambda v: float(len(v)),
    "min": min,
    "max": max,
}


CSV_OPS = (*AGGREGATES, "share", "pearson", "slope")


def _values(check: dict[str, Any], key: str = "values") -> list[float]:
    raw = require(check, key, list)
    if not raw:
        raise InputError(f"'{key}' must not be empty")
    return [number(v) for v in raw]


class DataError(InputError):
    """The data a check points at cannot be used. Reported on that check only."""


FILTER_OPS = ("equals", "not_equals", "in", "gt", "gte", "lt", "lte")


def _conditions(check: dict[str, Any]) -> list[dict[str, Any]]:
    """`filter` is one condition or a list of them, all of which must hold for a row."""
    raw = check.get("filter")
    if raw is None:
        return []
    conditions = raw if isinstance(raw, list) else [raw]
    for cond in conditions:
        if not isinstance(cond, dict) or not isinstance(cond.get("column"), str):
            raise InputError("each filter needs a 'column' and one of: " + ", ".join(FILTER_OPS))
        ops = [op for op in FILTER_OPS if op in cond]
        if len(ops) != 1 or set(cond) - {"column", *ops}:
            raise InputError(
                "each filter needs a 'column' and exactly one of: " + ", ".join(FILTER_OPS)
            )
        if ops[0] == "in" and not isinstance(cond["in"], list):
            raise InputError("filter 'in' must be an array")
    return conditions


def _holds(cond: dict[str, Any], row: dict[str, str | None]) -> bool:
    cell = (row.get(cond["column"]) or "").strip()
    if "equals" in cond:
        return cell == str(cond["equals"]).strip()
    if "not_equals" in cond:
        return cell != str(cond["not_equals"]).strip()
    if "in" in cond:
        return cell in {str(v).strip() for v in cond["in"]}
    op = next(op for op in ("gt", "gte", "lt", "lte") if op in cond)
    try:
        value, limit = number(cell.replace(",", "")), number(cond[op])
    except InputError:
        return False  # a blank or text cell is not in a numeric range
    return {"gt": value > limit, "gte": value >= limit, "lt": value < limit, "lte": value <= limit}[
        op
    ]


def _csv_rows(root: str | Path, check: dict[str, Any], columns: list[str]):
    """(line, row) for every row that passes the filter. Also returns the unfiltered row count."""
    path = inside(root, require(check, "path", str))
    conditions = _conditions(check)
    if not path.is_file():
        raise DataError(f"CSV file not found: {check['path']}")
    if path.stat().st_size > MAX_CSV_BYTES:
        raise DataError(f"CSV file is larger than {MAX_CSV_BYTES // 1024 // 1024} MiB")
    kept: list[tuple[int, dict[str, str | None]]] = []
    total = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        needed = [*columns, *(c["column"] for c in conditions)]
        for column in needed:
            if reader.fieldnames is None or column not in reader.fieldnames:
                raise DataError(f"Column '{column}' not found in {check['path']}")
        for line, row in enumerate(reader, start=2):
            total += 1
            if all(_holds(c, row) for c in conditions):
                kept.append((line, row))
    if conditions and not kept:
        raise DataError(f"The filter matched no rows in {check['path']}")
    return kept, total


def _numeric(
    rows: list[tuple[int, dict[str, str | None]]], column: str, path: str
) -> list[tuple[int, float]]:
    out = []
    for line, row in rows:
        cell = (row.get(column) or "").strip().replace(",", "")
        if not cell:
            continue  # blanks are skipped, and counted in the evidence
        try:
            out.append((line, number(cell)))
        except InputError:
            raise DataError(f"{path} line {line}: '{cell}' is not a number") from None
    return out


def _csv_column(root: str | Path, check: dict[str, Any]) -> list[float]:
    column = require(check, "column", str)
    rows, _ = _csv_rows(root, check, [column])
    values = [v for _, v in _numeric(rows, column, check["path"])]
    if not values:
        raise DataError(f"Column '{column}' has no numeric values")
    return values


def _csv_pair(root: str | Path, check: dict[str, Any]) -> tuple[list[float], list[float]]:
    """Rows where both columns hold a number: y from `column`, x from `column2`."""
    y_col, x_col = require(check, "column", str), require(check, "column2", str)
    rows, _ = _csv_rows(root, check, [y_col, x_col])
    ys, xs = dict(_numeric(rows, y_col, check["path"])), dict(_numeric(rows, x_col, check["path"]))
    lines = sorted(set(ys) & set(xs))
    if len(lines) < 3:
        raise DataError(f"Fewer than 3 rows have numbers in both '{y_col}' and '{x_col}'")
    return [ys[n] for n in lines], [xs[n] for n in lines]


def _csv_share(root: str | Path, check: dict[str, Any]) -> tuple[float, int, int]:
    """Percent of rows that pass `filter`, out of the rows that pass `within` (default: all).

    Only rows with something in `column` are counted, so a blank is neither in the numerator
    nor the denominator. `column` may hold text.
    """
    column = require(check, "column", str)
    conditions = _conditions(check)
    if not conditions:
        raise InputError("op 'share' needs a filter")
    scope = {**check, "filter": check.get("within")}
    rows, _ = _csv_rows(root, scope, [column, *(c["column"] for c in conditions)])
    counted = [row for _, row in rows if (row.get(column) or "").strip()]
    if not counted:
        raise DataError(f"Column '{column}' has no values in the rows counted")
    matched = sum(1 for row in counted if all(_holds(c, row) for c in conditions))
    return 100 * matched / len(counted), matched, len(counted)


def recalculate(kind: str, check: dict[str, Any], root: str | Path) -> tuple[float, dict[str, Any]]:
    """Return (expected value, extra evidence) for one check."""
    if kind == "percentage":
        top, bottom = number(check["numerator"]), number(check["denominator"])
        if bottom <= 0 or not 0 <= top <= bottom:
            raise InputError("percentage needs 0 <= numerator <= denominator and denominator > 0")
        return 100 * top / bottom, {}
    if kind == "ratio":
        top, bottom = number(check["numerator"]), number(check["denominator"])
        if bottom == 0:
            raise InputError("ratio needs a non-zero denominator")
        return top / bottom, {}
    if kind == "difference":
        return number(check["a"]) - number(check["b"]), {}
    if kind == "percent_change":
        old, new = number(check["old"]), number(check["new"])
        if old == 0:
            raise InputError("percent_change needs a non-zero old value")
        return (new - old) / abs(old) * 100, {}
    if kind in AGGREGATES:
        return AGGREGATES[kind](_values(check)), {"n": len(check["values"])}
    if kind == "csv":
        op = require(check, "op", str)
        if op not in CSV_OPS:
            raise InputError("csv op must be one of: " + ", ".join(CSV_OPS))
        evidence: dict[str, Any] = {"file": check["path"], "column": check["column"], "op": op}
        for key in ("filter", "within"):
            if check.get(key) is not None:
                evidence[key] = check[key]
        if op == "share":
            value, matched, total = _csv_share(root, check)
            return value, {**evidence, "rows_matching": matched, "rows_used": total}
        if op in ("pearson", "slope"):
            ys, xs = _csv_pair(root, check)
            evidence.update(column2=check["column2"], rows_used=len(ys))
            if op == "pearson":
                try:
                    return statistics.correlation(xs, ys), evidence
                except statistics.StatisticsError:
                    raise DataError(
                        "A column is constant, so the correlation is undefined"
                    ) from None
            try:
                return statistics.linear_regression(xs, ys).slope, evidence
            except statistics.StatisticsError:
                raise DataError("'column2' is constant, so the slope is undefined") from None
        values = _csv_column(root, check)
        return AGGREGATES[op](values), {**evidence, "rows_used": len(values)}
    if kind == "match":
        return number(check["source_value"]), {}
    raise InputError(f"Unknown check type: {kind}")


def tolerance_for(check: dict[str, Any]) -> float:
    """`decimals` means 'the report rounded to this many places', so allow half a unit."""
    if "decimals" in check:
        decimals = check["decimals"]
        if type(decimals) is not int or not 0 <= decimals <= 12:
            raise InputError("decimals must be an integer from 0 to 12")
        return 0.5 * 10**-decimals + 1e-12
    tolerance = number(check.get("tolerance", DEFAULT_TOLERANCE))
    if tolerance < 0:
        raise InputError("tolerance must not be negative")
    return tolerance


def rounded(value: float, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals)
    return str(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def dataproof(data: dict[str, Any], root: str | Path = ".") -> dict[str, Any]:
    checks = require(data, "checks", list)
    out: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        kind = require(check, "type", str)
        reported = number(check.get("reported"))
        try:
            expected, extra = recalculate(kind, check, root)
        except KeyError as exc:
            raise InputError(f"Check {index} ({kind}) is missing {exc.args[0]!r}") from None
        except DataError as exc:
            # The checks file is fine; this check's data is not. Say so and carry on.
            out.append(
                finding(
                    "ERROR",
                    str(exc),
                    type=kind,
                    reported=reported,
                    label=check.get("label"),
                    lineage=check.get("lineage", []),
                )
            )
            continue
        tolerance = tolerance_for(check)
        passed = abs(expected - reported) <= tolerance
        evidence: dict[str, Any] = {
            "type": kind,
            "reported": reported,
            "expected": expected,
            "difference": reported - expected,
            "tolerance": tolerance,
            "label": check.get("label"),
            "lineage": check.get("lineage", []),
            **extra,
        }
        if "decimals" in check:
            evidence["expected_rounded"] = rounded(expected, check["decimals"])
        out.append(
            finding(
                "PASS" if passed else "MISMATCH",
                "Recalculated from the supplied data.",
                **evidence,
            )
        )
    if not checks:
        out.append(finding("NEEDS_REVIEW", "No checks were supplied."))
    errored = sum(1 for f in out if f["status"] == "ERROR")
    return report(
        "DataProof",
        out,
        coverage=coverage(
            "checks",
            len(checks),
            len(checks) - errored,
            {"data_unusable": errored},
            notes=[
                "only the claims written as checks were examined; claims with no check "
                "(for example t-tests) were not"
            ],
        ),
        scope="recalculation only; does not judge whether the right quantity was reported",
    )
