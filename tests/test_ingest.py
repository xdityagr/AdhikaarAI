"""
Corpus ingest tests.

Runs against a real NSFDC workbook saved to tests/fixtures/, so the suite never
touches the network — a government website being slow must not make the test
suite flaky, which is the same reason it must not block a beneficiary.

The parsers are where the bugs live. Two real ones were caught here:

1. The title row reads "DISBURSEMENT : NOTIONAL ALLOCATION VS ACTUALS" and
   contains both header keywords, so a substring match picked row 0 as the
   header and found no columns at all.
2. The sheet stacks SEVERAL tables, each with its own header and its own 5-year
   range. Parsing one header and reading to end-of-file applied the wrong column
   mapping to every later block — 135 "states" per year, and utilisation
   figures in the thousands of percent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.corpus.ingest import (
    StateUtilisation,
    _clean_number,
    _pick_allocation_workbook,
    DiscoveredFile,
    parse_state_utilisation,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nsfdc_allocation_vs_actuals.xlsx"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="NSFDC workbook fixture not present",
)


@pytest.fixture(scope="module")
def rows() -> list[StateUtilisation]:
    return parse_state_utilisation(FIXTURE.read_bytes(), source_url="fixture")


# ---------------------------------------------------------------------------
# Shape — the two bugs above would both show up here
# ---------------------------------------------------------------------------

class TestWorkbookShape:
    """India has ~36 states and union territories. Not 135."""

    def test_thirty_six_states_per_year(self, rows):
        by_year: dict[str, int] = {}
        for row in rows:
            by_year[row.financial_year] = by_year.get(row.financial_year, 0) + 1
        for year, count in by_year.items():
            assert count <= 36, f"{year} has {count} states — column mapping is wrong"

    def test_covers_the_current_financial_year(self, rows):
        years = {r.financial_year for r in rows}
        assert "2025-2026" in years
        assert "2026-2027" in years

    def test_aggregate_rows_are_excluded(self, rows):
        names = {r.state.lower().rstrip(" :") for r in rows}
        assert "total" not in names
        assert "grand total" not in names


# ---------------------------------------------------------------------------
# Values — spot-checked against the raw cells
# ---------------------------------------------------------------------------

class TestParsedValues:
    """Verified by eye against the workbook: row 5, block 1."""

    def test_andhra_pradesh_2025_26(self, rows):
        row = next(r for r in rows
                   if r.state == "Andhra Pradesh" and r.financial_year == "2025-2026")
        assert row.allocation_lakh == pytest.approx(3442.49, abs=0.01)
        assert row.actual_lakh == pytest.approx(7516.18, abs=0.01)
        assert row.utilisation_pct == pytest.approx(218.34, abs=0.01)

    def test_andhra_pradesh_2022_23(self, rows):
        row = next(r for r in rows
                   if r.state == "Andhra Pradesh" and r.financial_year == "2022-2023")
        assert row.allocation_lakh == pytest.approx(3755.44, abs=0.01)
        assert row.utilisation_pct == pytest.approx(40.43, abs=0.01)

    def test_published_percentage_matches_the_ratio(self, rows):
        """The self-consistency guard: a misaligned column would break this."""
        for row in rows:
            if row.allocation_lakh:
                derived = row.actual_lakh / row.allocation_lakh * 100.0
                assert abs(row.utilisation_pct - derived) <= 1.0, row


# ---------------------------------------------------------------------------
# The prudential signal — what the router actually consumes
# ---------------------------------------------------------------------------

class TestSCAUtilisationNorm:
    """Fresh NSFDC releases require 100% cumulative utilisation of prior funds.

    This is the real rule running on real published data — the upgrade from the
    previous design, which built the rule and mocked the numbers.
    """

    def test_norm_boundary(self):
        at = StateUtilisation("X", "2025-2026", 100.0, 100.0, 100.0)
        under = StateUtilisation("X", "2025-2026", 100.0, 99.0, 99.0)
        assert at.meets_sca_utilisation_norm
        assert not under.meets_sca_utilisation_norm

    def test_real_data_splits_states_both_ways(self, rows):
        """The demo needs both an eligible and an excluded partner to exist."""
        latest = [r for r in rows if r.financial_year == "2025-2026"]
        eligible = [r for r in latest if r.meets_sca_utilisation_norm]
        excluded = [r for r in latest if not r.meets_sca_utilisation_norm]
        assert eligible, "No state meets the norm — the demo has nothing to route to"
        assert excluded, "No state fails the norm — the demo has nothing to exclude"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_clean_number_handles_spreadsheet_junk(self):
        assert _clean_number("1,234.5") == 1234.5
        assert _clean_number(None) is None
        assert _clean_number("nan") is None
        assert _clean_number("-") is None
        assert _clean_number("") is None

    def test_workbook_picker_prefers_the_allocation_file(self):
        files = [
            DiscoveredFile("Year-wise Disbursement", "u1", ".xlsx"),
            DiscoveredFile("State-wise Notional Allocation vs Actuals", "u2", ".xlsx"),
            DiscoveredFile("Some report", "u3", ".pdf"),
        ]
        assert _pick_allocation_workbook(files).url == "u2"

    def test_workbook_picker_ignores_pdfs(self):
        assert _pick_allocation_workbook([DiscoveredFile("x", "u", ".pdf")]) is None
