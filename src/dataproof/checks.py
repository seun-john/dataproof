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

from .core import InputError, finding, inside, number, report, require

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


def _values(check: dict[str, Any], key: str = "values") -> list[float]:
    raw = require(check, key, list)
    if not raw:
        raise InputError(f"'{key}' must not be empty")
    return [number(v) for v in raw]


def _csv_column(root: str | Path, check: dict[str, Any]) -> list[float]:
    path = inside(root, require(check, "path", str))
    column = require(check, "column", str)
    if not path.is_file():
        raise InputError(f"CSV file not found: {check['path']}")
    if path.stat().st_size > MAX_CSV_BYTES:
        raise InputError(f"CSV file is larger than {MAX_CSV_BYTES // 1024 // 1024} MiB")
    values: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise InputError(f"Column '{column}' not found in {check['path']}")
        for line, row in enumerate(reader, start=2):
            cell = (row.get(column) or "").strip().replace(",", "")
            if not cell:
                continue  # blanks are skipped, and counted in the evidence
            try:
                values.append(number(cell))
            except InputError:
                raise InputError(f"{check['path']} line {line}: '{cell}' is not a number") from None
    if not values:
        raise InputError(f"Column '{column}' has no numeric values")
    return values


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
        if op not in AGGREGATES:
            raise InputError("csv op must be one of: " + ", ".join(AGGREGATES))
        values = _csv_column(root, check)
        return AGGREGATES[op](values), {
            "file": check["path"],
            "column": check["column"],
            "op": op,
            "rows_used": len(values),
        }
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
    return report(
        "DataProof",
        out,
        scope="recalculation only; does not judge whether the right quantity was reported",
    )
