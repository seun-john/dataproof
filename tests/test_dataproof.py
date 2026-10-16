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


def test_csv_data_errors_are_reported_on_that_check(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\nabc\n")
    base = {"type": "csv", "path": "d.csv", "op": "sum", "reported": 1}
    for check, message in [
        ({**base, "column": "a"}, "line 3"),
        ({**base, "column": "zzz"}, "not found"),
        ({**base, "path": "missing.csv", "column": "a"}, "not found"),
    ]:
        f = one(check, tmp_path)
        assert f["status"] == "ERROR" and message in f["message"], check
        assert f["evidence"]["reported"] == 1


def test_unusable_checks_file_is_still_rejected(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\n")
    base = {"type": "csv", "path": "d.csv", "column": "a", "reported": 1}
    with pytest.raises(InputError):
        one({**base, "op": "stdev"}, tmp_path)
    with pytest.raises(InputError):
        one({**base}, tmp_path)  # no op


def test_one_unreadable_csv_does_not_stop_the_other_checks(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\n2\n")
    checks = [
        {"type": "csv", "path": "d.csv", "column": "a", "op": "sum", "reported": 3},
        {"type": "csv", "path": "gone.csv", "column": "a", "op": "sum", "reported": 3},
        {"type": "sum", "values": [1, 2], "reported": 4},
    ]
    statuses = [f["status"] for f in dataproof({"checks": checks}, tmp_path)["findings"]]
    assert statuses == ["PASS", "ERROR", "MISMATCH"]


GROUPS = (
    "station,score,hours\n"
    "North,10,1\nNorth,20,2\nNorth,30,3\n"
    "South,40,4\nSouth,50,5\n"
    "East,,6\nEast,70,7\n"
)


def csv_check(tmp_path: Path, **kw: Any) -> dict[str, Any]:
    write_csv(tmp_path / "g.csv", GROUPS)
    base = {"type": "csv", "path": "g.csv", "column": "score", "op": "mean", "reported": 0}
    return one({**base, **kw}, tmp_path)


def test_filter_restricts_the_rows_used(tmp_path: Path) -> None:
    f = csv_check(
        tmp_path, filter={"column": "station", "equals": "North"}, reported=20, decimals=1
    )
    assert f["status"] == "PASS"
    assert f["evidence"]["rows_used"] == 3
    assert f["evidence"]["filter"] == {"column": "station", "equals": "North"}
    wrong = csv_check(tmp_path, filter={"column": "station", "equals": "North"}, reported=35)
    assert wrong["status"] == "MISMATCH"


@pytest.mark.parametrize(
    ("flt", "op", "expected"),
    [
        ({"column": "station", "not_equals": "North"}, "count", 3),  # East's blank is skipped
        ({"column": "station", "in": ["North", "South"]}, "sum", 150),
        ({"column": "hours", "gt": 4}, "sum", 120),
        ({"column": "hours", "gte": 4}, "sum", 160),
        ({"column": "hours", "lt": 3}, "max", 20),
        ({"column": "hours", "lte": 3}, "sum", 60),
        (
            [{"column": "station", "in": ["North", "East"]}, {"column": "hours", "gt": 2}],
            "sum",
            100,
        ),
    ],
)
def test_filter_operators(tmp_path: Path, flt: Any, op: str, expected: float) -> None:
    f = csv_check(tmp_path, filter=flt, op=op, reported=expected)
    assert f["status"] == "PASS", f


def test_share_is_a_percentage_of_rows(tmp_path: Path) -> None:
    # 6 rows have a score; 3 are North
    f = csv_check(
        tmp_path,
        op="share",
        filter={"column": "station", "equals": "North"},
        reported=50.0,
        decimals=1,
    )
    assert f["status"] == "PASS"
    assert (f["evidence"]["rows_matching"], f["evidence"]["rows_used"]) == (3, 6)
    off = csv_check(
        tmp_path,
        op="share",
        filter={"column": "station", "equals": "North"},
        reported=60.0,
        decimals=1,
    )
    assert off["status"] == "MISMATCH"


def test_share_within_a_group_on_a_text_column(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "t.csv",
        "station,member\nCampus,Yes\nCampus,No\nCampus,Yes\nCampus,\nQuay,Yes\nQuay,Yes\n",
    )
    base = {"type": "csv", "path": "t.csv", "column": "member", "op": "share"}
    f = one(
        {
            **base,
            "filter": {"column": "member", "equals": "Yes"},
            "within": {"column": "station", "equals": "Campus"},
            "reported": 66.7,
            "decimals": 1,
        },
        tmp_path,
    )  # the blank Campus row is not counted: 2 of 3
    assert f["status"] == "PASS"
    assert (f["evidence"]["rows_matching"], f["evidence"]["rows_used"]) == (2, 3)
    assert f["evidence"]["within"] == {"column": "station", "equals": "Campus"}
    overall = one(
        {**base, "filter": {"column": "member", "equals": "Yes"}, "reported": 80.0, "decimals": 1},
        tmp_path,
    )
    assert overall["status"] == "PASS"  # 4 of 5 rows with a value


def test_share_within_a_group_that_does_not_exist_is_a_check_error(tmp_path: Path) -> None:
    write_csv(tmp_path / "t.csv", "station,member\nCampus,Yes\n")
    f = one(
        {
            "type": "csv", "path": "t.csv", "column": "member", "op": "share", "reported": 1,
            "filter": {"column": "member", "equals": "Yes"},
            "within": {"column": "station", "equals": "Nowhere"},
        },
        tmp_path,
    )  # fmt: skip
    assert f["status"] == "ERROR" and "matched no rows" in f["message"]


def test_share_without_a_filter_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="needs a filter"):
        csv_check(tmp_path, op="share", reported=100)


def test_pearson_and_slope(tmp_path: Path) -> None:
    write_csv(tmp_path / "x.csv", "y,x\n2,1\n4,2\n6,3\n8,4\n")
    base = {"type": "csv", "path": "x.csv", "column": "y", "column2": "x"}
    r = one({**base, "op": "pearson", "reported": 1.0, "decimals": 3}, tmp_path)
    assert r["status"] == "PASS" and r["evidence"]["column2"] == "x"
    slope = one({**base, "op": "slope", "reported": 2.0, "decimals": 2}, tmp_path)
    assert slope["status"] == "PASS"
    wrong = one({**base, "op": "slope", "reported": 2.5, "decimals": 2}, tmp_path)
    assert wrong["status"] == "MISMATCH"


def test_pearson_uses_only_rows_with_both_numbers_and_the_filter(tmp_path: Path) -> None:
    write_csv(tmp_path / "x.csv", "g,y,x\na,1,1\na,2,2\na,3,3\na,,4\nb,9,1\nb,1,2\nb,9,3\n")
    f = one(
        {
            "type": "csv", "path": "x.csv", "column": "y", "column2": "x", "op": "pearson",
            "filter": {"column": "g", "equals": "a"}, "reported": 1.0, "decimals": 3,
        },
        tmp_path,
    )  # fmt: skip
    assert f["status"] == "PASS" and f["evidence"]["rows_used"] == 3


def test_undefined_statistics_and_empty_filters_are_check_errors(tmp_path: Path) -> None:
    write_csv(tmp_path / "x.csv", "g,y,x\na,1,5\na,2,5\na,3,5\n")
    base = {"type": "csv", "path": "x.csv", "column": "y", "column2": "x", "reported": 0}
    assert "constant" in one({**base, "op": "pearson"}, tmp_path)["message"]
    assert "constant" in one({**base, "op": "slope"}, tmp_path)["message"]
    none = one({**base, "op": "mean", "filter": {"column": "g", "equals": "zzz"}}, tmp_path)
    assert none["status"] == "ERROR" and "matched no rows" in none["message"]
    short = one({**base, "op": "pearson", "filter": {"column": "y", "gt": 2}}, tmp_path)
    assert short["status"] == "ERROR" and "Fewer than 3" in short["message"]


@pytest.mark.parametrize(
    "bad",
    [
        {"column": "g"},
        {"column": "g", "equals": "a", "gt": 1},
        {"equals": "a"},
        {"column": "g", "in": "a"},
        {"column": "g", "equals": "a", "extra": 1},
        "g=a",
    ],
)
def test_malformed_filters_are_rejected(tmp_path: Path, bad: Any) -> None:
    write_csv(tmp_path / "x.csv", "g,y\na,1\n")
    check = {"type": "csv", "path": "x.csv", "column": "y", "op": "sum", "reported": 1}
    with pytest.raises(InputError):
        one({**check, "filter": bad}, tmp_path)


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


def test_coverage_counts_checks_decided_and_unusable(tmp_path: Path) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\n2\n")
    checks = [
        {"type": "csv", "path": "d.csv", "column": "a", "op": "sum", "reported": 3},  # pass
        {"type": "sum", "values": [1, 2], "reported": 4},  # mismatch: still decided
        {"type": "csv", "path": "gone.csv", "column": "a", "op": "sum", "reported": 3},  # error
        {"type": "csv", "path": "d.csv", "column": "zzz", "op": "sum", "reported": 3},  # error
    ]
    block = dataproof({"checks": checks}, tmp_path)["coverage"]
    assert (block["unit"], block["items"], block["decided"], block["undecided"]) == (
        "checks",
        4,
        2,
        2,
    )
    assert block["reasons"] == {"data_unusable": 2}
    assert block["suppressed"] == 0
    assert block["decided"] + block["undecided"] == block["items"]
    assert sum(block["reasons"].values()) == block["undecided"]


def test_coverage_with_no_checks_has_no_items() -> None:
    block = dataproof({"checks": []})["coverage"]
    assert (block["items"], block["decided"], block["undecided"], block["reasons"]) == (0, 0, 0, {})


def test_cli_min_coverage_and_the_stderr_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_csv(tmp_path / "d.csv", "a\n1\n2\n")
    checks = [
        {"type": "csv", "path": "d.csv", "column": "a", "op": "sum", "reported": 3},
        {"type": "csv", "path": "gone.csv", "column": "a", "op": "sum", "reported": 3},
    ]
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"checks": checks}), encoding="utf-8")
    base = ["check", str(src), "--root", str(tmp_path), "-o", str(tmp_path / "r.json")]
    assert main([*base, "--min-coverage", "50"]) == 0  # 1 of 2 = 50%
    assert "coverage: decided 1 of 2 checks; 1 could not be checked (data_unusable 1)" in (
        capsys.readouterr().err
    )
    assert main([*base, "--min-coverage", "51"]) == 3
    assert main([*base]) == 0  # opt-in
    # a --strict failure still wins over low coverage
    assert main([*base, "--strict", "--min-coverage", "100"]) == 1
    written = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert written["coverage"]["items"] == 2


def test_html_report_shows_the_coverage_line(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"checks": [{"type": "sum", "values": [1], "reported": 1}]}), "utf-8")
    page = tmp_path / "r.html"
    assert main(["check", str(src), "-o", str(tmp_path / "r.json"), "--html", str(page)]) == 0
    assert "decided 1 of 1 checks" in page.read_text(encoding="utf-8")


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
