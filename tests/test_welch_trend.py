"""Welch t-test, p-values and period-pattern checks."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from dataproof.checks import betainc, dataproof, t_two_sided_p, welch
from dataproof.cli import main


def one(check: dict[str, Any], root: Path | str = ".") -> dict[str, Any]:
    return dataproof({"checks": [check]}, root)["findings"][0]


class TestTDistribution:
    @pytest.mark.parametrize("t", [0.3, 1.0, 2.5, 12.0])
    def test_one_degree_of_freedom_is_the_cauchy_distribution(self, t: float) -> None:
        assert t_two_sided_p(t, 1) == pytest.approx(1 - 2 / math.pi * math.atan(t), abs=1e-10)

    @pytest.mark.parametrize("t", [0.3, 1.0, 2.5, 12.0])
    def test_two_degrees_of_freedom_has_a_closed_form(self, t: float) -> None:
        assert t_two_sided_p(t, 2) == pytest.approx(1 - t / math.sqrt(2 + t * t), abs=1e-10)

    def test_table_values(self) -> None:
        assert t_two_sided_p(2.228138852, 10) == pytest.approx(0.05, abs=1e-8)
        assert t_two_sided_p(1.959964, 1e7) == pytest.approx(0.05, abs=1e-5)
        assert t_two_sided_p(0.0, 7.3) == 1.0

    def test_the_sign_of_t_does_not_matter(self) -> None:
        assert t_two_sided_p(-1.8, 12.5) == pytest.approx(t_two_sided_p(1.8, 12.5))

    def test_fractional_degrees_of_freedom_lie_between_neighbours(self) -> None:
        low, mid, high = (t_two_sided_p(2.0, df) for df in (10, 10.5, 11))
        assert high < mid < low

    def test_incomplete_beta_edges(self) -> None:
        assert betainc(2, 3, 0) == 0.0 and betainc(2, 3, 1) == 1.0
        assert betainc(1, 1, 0.37) == pytest.approx(0.37)


def test_welch_by_hand() -> None:
    t, df = welch([1, 2, 3], [2, 4, 6])
    assert t == pytest.approx(-2 / math.sqrt(5 / 3))
    assert df == pytest.approx(50 / 17)


CSV = (
    "g,x\n"
    + "".join(f"A,{v}\n" for v in (1, 2, 3))
    + "".join(f"B,{v}\n" for v in (2, 4, 6))
    + "C,9\n"
)


def welch_check(op: str, reported: float, **extra: Any) -> dict[str, Any]:
    return {
        "type": "csv",
        "path": "d.csv",
        "column": "x",
        "group_column": "g",
        "groups": ["A", "B"],
        "op": op,
        "reported": reported,
        **extra,
    }


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "d.csv").write_text(CSV, encoding="utf-8")
    return tmp_path


class TestWelchChecks:
    def test_t_passes_and_shows_the_groups(self, root: Path) -> None:
        f = one(welch_check("welch_t", -1.55, decimals=2), root)
        assert f["status"] == "PASS"
        assert f["evidence"]["n"] == [3, 3] and f["evidence"]["groups"] == ["A", "B"]
        assert f["evidence"]["df"] == pytest.approx(2.941, abs=1e-3)

    def test_the_order_of_the_groups_sets_the_sign(self, root: Path) -> None:
        assert one(welch_check("welch_t", 1.55, decimals=2), root)["status"] == "MISMATCH"
        swapped = welch_check("welch_t", 1.55, decimals=2, groups=["B", "A"])
        assert one(swapped, root)["status"] == "PASS"

    def test_transposed_digits_are_a_mismatch(self, root: Path) -> None:
        assert one(welch_check("welch_t", -1.45, decimals=2), root)["status"] == "MISMATCH"

    def test_p_is_two_sided_unless_tails_say_otherwise(self, root: Path) -> None:
        two = t_two_sided_p(*welch([1, 2, 3], [2, 4, 6]))
        assert one(welch_check("welch_p", round(two, 3), decimals=3), root)["status"] == "PASS"
        assert (
            one(welch_check("welch_p", round(two / 2, 3), decimals=3), root)["status"] == "MISMATCH"
        )
        half = welch_check("welch_p", round(two / 2, 3), decimals=3, tails=1)
        assert one(half, root)["status"] == "PASS"

    def test_a_bad_tails_value_is_a_malformed_check(self, root: Path) -> None:
        from dataproof.core import InputError

        with pytest.raises(InputError):
            one(welch_check("welch_p", 0.1, tails=3), root)

    def test_a_group_with_one_value_is_an_error_on_that_check(self, root: Path) -> None:
        f = one(welch_check("welch_t", 0.0, groups=["A", "C"]), root)
        assert f["status"] == "ERROR" and "fewer than 2" in f["message"]

    def test_two_constant_groups_are_an_error_not_a_crash(self, tmp_path: Path) -> None:
        (tmp_path / "d.csv").write_text("g,x\nA,1\nA,1\nB,1\nB,1\n", encoding="utf-8")
        assert one(welch_check("welch_t", 0.0), tmp_path)["status"] == "ERROR"

    def test_the_filter_applies_before_the_groups(self, root: Path) -> None:
        f = one(welch_check("welch_t", 0.0, filter={"column": "x", "gt": 100}), root)
        assert f["status"] == "ERROR"

    def test_identical_groups_give_t_zero_and_p_one(self, tmp_path: Path) -> None:
        (tmp_path / "d.csv").write_text("g,x\nA,1\nA,3\nB,1\nB,3\n", encoding="utf-8")
        assert one(welch_check("welch_t", 0.0), tmp_path)["status"] == "PASS"
        assert one(welch_check("welch_p", 1.0), tmp_path)["status"] == "PASS"


TREND = "q,v\nQ1,10\nQ1,5\nQ2,20\nQ3,12\nQ3,1\nQ4,30\n"


def trend_check(pattern: str, periods: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "type": "trend",
        "path": "t.csv",
        "column": "v",
        "period_column": "q",
        "periods": periods,
        "pattern": pattern,
        **extra,
    }


@pytest.fixture
def troot(tmp_path: Path) -> Path:
    (tmp_path / "t.csv").write_text(TREND, encoding="utf-8")
    return tmp_path


class TestTrend:
    def test_totals_per_period_are_shown(self, troot: Path) -> None:
        f = one(trend_check("rising", ["Q1", "Q2"]), troot)
        assert f["status"] == "PASS" and f["evidence"]["totals"] == {"Q1": 15.0, "Q2": 20.0}

    def test_rising_needs_every_step_to_rise(self, troot: Path) -> None:
        assert one(trend_check("rising", ["Q1", "Q2", "Q3"]), troot)["status"] == "MISMATCH"
        assert one(trend_check("rising", ["Q3", "Q2", "Q4"]), troot)["status"] == "PASS"

    def test_falling(self, troot: Path) -> None:
        assert one(trend_check("falling", ["Q2", "Q3"]), troot)["status"] == "PASS"
        assert one(trend_check("falling", ["Q4", "Q2", "Q3"]), troot)["status"] == "PASS"
        assert one(trend_check("falling", ["Q1", "Q2"]), troot)["status"] == "MISMATCH"

    def test_peak_and_trough(self, troot: Path) -> None:
        assert one(trend_check("peak", ["Q1", "Q2", "Q3"], at="Q2"), troot)["status"] == "PASS"
        assert one(trend_check("peak", ["Q1", "Q2", "Q3"], at="Q1"), troot)["status"] == "MISMATCH"
        assert one(trend_check("trough", ["Q2", "Q3", "Q4"], at="Q3"), troot)["status"] == "PASS"

    def test_a_tie_is_not_a_rise(self, tmp_path: Path) -> None:
        (tmp_path / "t.csv").write_text("q,v\nA,5\nB,5\n", encoding="utf-8")
        assert one(trend_check("rising", ["A", "B"]), tmp_path)["status"] == "MISMATCH"

    def test_mean_instead_of_sum(self, troot: Path) -> None:
        f = one(trend_check("falling", ["Q1", "Q2"], agg="mean"), troot)
        assert f["status"] == "MISMATCH" and f["evidence"]["totals"]["Q1"] == 7.5

    def test_a_missing_period_is_an_error_on_that_check(self, troot: Path) -> None:
        f = one(trend_check("rising", ["Q1", "Q9"]), troot)
        assert f["status"] == "ERROR" and "Q9" in f["message"]

    @pytest.mark.parametrize(
        "bad",
        [
            {"pattern": "sideways"},
            {"periods": ["Q1"]},
            {"periods": ["Q1", "Q1"]},
            {"pattern": "peak", "periods": ["Q1", "Q2"], "at": "Q1"},
            {"pattern": "peak", "periods": ["Q1", "Q2", "Q3"], "at": "Q9"},
            {"agg": "max"},
        ],
    )
    def test_malformed_trend_checks_are_refused(self, troot: Path, bad: dict[str, Any]) -> None:
        from dataproof.core import InputError

        check = {**trend_check("rising", ["Q1", "Q2", "Q3"]), **bad}
        with pytest.raises(InputError):
            one(check, troot)

    def test_trend_needs_no_reported_value_and_counts_in_coverage(self, troot: Path) -> None:
        result = dataproof(
            {"checks": [trend_check("rising", ["Q1", "Q2"]), trend_check("rising", ["Q1", "Q9"])]},
            troot,
        )
        assert result["coverage"]["items"] == 2 and result["coverage"]["decided"] == 1

    def test_cli_runs_a_trend_and_a_welch_check(
        self, root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        (root / "t.csv").write_text(TREND, encoding="utf-8")
        checks = {
            "checks": [
                trend_check("rising", ["Q1", "Q2"]),
                welch_check("welch_t", -1.55, decimals=2),
            ]
        }
        (root / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
        code = main(["check", str(root / "checks.json"), "--root", str(root), "--strict"])
        assert code == 0
        assert '"PASS"' in capsys.readouterr().out
