from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dataproof.checks import dataproof, rounded
from dataproof.cli import main
from dataproof.core import InputError


def one(check: dict[str, Any], root: Path | str = ".") -> dict[str, Any]:
    return dataproof({"checks": [check]}, root)["findings"][0]


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        ({"type": "percentage", "numerator": 45, "denominator": 60}, 75.0),
        ({"type": "ratio", "numerator": 1, "denominator": 4}, 0.25),
        ({"type": "difference", "a": 10, "b": 3.5}, 6.5),
        ({"type": "percent_change", "old": 50, "new": 60}, 20.0),
        ({"type": "percent_change", "old": -50, "new": -40}, 20.0),
        ({"type": "sum", "values": [1, 2, 3.5]}, 6.5),
        ({"type": "mean", "values": [2, 4, 9]}, 5.0),
        ({"type": "median", "values": [1, 100, 3]}, 3.0),
        ({"type": "count", "values": [5, 5, 5]}, 3.0),
        ({"type": "min", "values": [4, 2, 8]}, 2.0),
        ({"type": "max", "values": [4, 2, 8]}, 8.0),
        ({"type": "match", "source_value": 7.25}, 7.25),
    ],
)
def test_recalculation(check: dict[str, Any], expected: float) -> None:
    f = one({**check, "reported": expected})
    assert f["status"] == "PASS"
    assert f["evidence"]["expected"] == pytest.approx(expected)


def test_mismatch_shows_the_difference() -> None:
    f = one({"type": "sum", "values": [1, 2], "reported": 4})
    assert f["status"] == "MISMATCH"
    assert f["evidence"]["difference"] == 1


def test_default_tolerance_is_small_but_not_zero() -> None:
    assert one({"type": "mean", "values": [1, 2, 2], "reported": 1.67})["status"] == "PASS"
    assert one({"type": "mean", "values": [1, 2, 2], "reported": 1.8})["status"] == "MISMATCH"


def test_decimals_compare_at_the_precision_reported() -> None:
    # 2/3 = 66.666..., reported as 66.7 to one decimal place
    check = {"type": "percentage", "numerator": 2, "denominator": 3, "decimals": 1}
    assert one({**check, "reported": 66.7})["status"] == "PASS"
    assert one({**check, "reported": 66.6})["status"] == "MISMATCH"
    assert one({**check, "reported": 66.7})["evidence"]["expected_rounded"] == "66.7"


def test_half_up_rounding_helper() -> None:
    assert rounded(2.5, 0) == "3"
    assert rounded(0.125, 2) == "0.13"


@pytest.mark.parametrize(
    "check",
    [
        {"type": "percentage", "numerator": 5, "denominator": 0, "reported": 1},
        {"type": "percentage", "numerator": 7, "denominator": 5, "reported": 1},
        {"type": "ratio", "numerator": 1, "denominator": 0, "reported": 1},
        {"type": "percent_change", "old": 0, "new": 1, "reported": 1},
        {"type": "mean", "values": [], "reported": 1},
        {"type": "sum", "values": [1, True], "reported": 1},
        {"type": "sum", "values": [1, float("nan")], "reported": 1},
        {"type": "sum", "values": [1], "reported": 1, "tolerance": -1},
        {"type": "sum", "values": [1], "reported": 1, "decimals": 1.5},
        {"type": "sum", "reported": 1},
        {"type": "teleport", "reported": 1},
        {"type": "sum", "values": [1]},
    ],
)
def test_bad_input_is_rejected(check: dict[str, Any]) -> None:
    with pytest.raises(InputError):
        one(check)


def write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_csv_column_checks(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", 'id,amount\n1,"1,200"\n2,300\n3,\n4,500.5\n')
    f = one(
        {"type": "csv", "path": "d.csv", "column": "amount", "op": "sum", "reported": 2000.5},
        tmp_path,
    )
    assert f["status"] == "PASS"
    assert f["evidence"]["rows_used"] == 3
    count = one(
        {"type": "csv", "path": "d.csv", "column": "id", "op": "count", "reported": 4}, tmp_path
    )
    assert count["status"] == "PASS"


def test_csv_with_a_byte_order_mark(tmp_path: Path) -> None:
    (tmp_path / "d.csv").write_bytes("﻿x\n1\n2\n".encode())
    f = one({"type": "csv", "path": "d.csv", "column": "x", "op": "sum", "reported": 3}, tmp_path)
    assert f["status"] == "PASS"


def test_csv_errors(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\nabc\n")
    base = {"type": "csv", "path": "d.csv", "op": "sum", "reported": 1}
    with pytest.raises(InputError, match="line 3"):
        one({**base, "column": "a"}, tmp_path)
    with pytest.raises(InputError, match="not found"):
        one({**base, "column": "zzz"}, tmp_path)
    with pytest.raises(InputError, match="not found"):
        one({**base, "path": "missing.csv", "column": "a"}, tmp_path)
    with pytest.raises(InputError):
        one({**base, "column": "a", "op": "stdev"}, tmp_path)


def test_csv_cannot_escape_the_root(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    write_csv(tmp_path / "secret.csv", "a\n1\n")
    check = {"type": "csv", "path": "../secret.csv", "column": "a", "op": "sum", "reported": 1}
    with pytest.raises(InputError, match="escapes"):
        one(check, root)


def test_empty_check_list_needs_review() -> None:
    assert dataproof({"checks": []})["findings"][0]["status"] == "NEEDS_REVIEW"


def test_lineage_and_label_are_kept() -> None:
    f = one(
        {
            "type": "sum",
            "values": [1],
            "reported": 1,
            "label": "Table 2 total",
            "lineage": ["raw.xlsx!B2"],
        }
    )
    assert f["evidence"]["label"] == "Table 2 total"
    assert f["evidence"]["lineage"] == ["raw.xlsx!B2"]


def test_cli_strict_and_root(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "x\n1\n2\n")
    src = tmp_path / "in.json"
    good = {"type": "csv", "path": "d.csv", "column": "x", "op": "sum", "reported": 3}
    src.write_text(json.dumps({"checks": [good]}), encoding="utf-8")
    out = tmp_path / "out" / "r.json"
    assert main(["check", str(src), "--root", str(tmp_path), "--strict", "-o", str(out)]) == 0
    src.write_text(json.dumps({"checks": [{**good, "reported": 4}]}), encoding="utf-8")
    assert main(["check", str(src), "--root", str(tmp_path), "-o", str(out)]) == 0
    assert main(["check", str(src), "--root", str(tmp_path), "--strict", "-o", str(out)]) == 1
    assert main(["check", str(src), "--root", str(tmp_path), "-o", str(src)]) == 2
