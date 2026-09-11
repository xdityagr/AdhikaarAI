"""
Corpus integrity tests.

The corpus is the single source of truth for every scheme number, so these tests
guard the data itself rather than any behaviour built on it:

1. It loads and validates at all
2. All five schemes are present (the PS names three; NSFDC publishes five)
3. Every scheme declares project_types — the anti-silent-default guard
4. Provenance is present, because a number without a source is how docs/rules.md
   burned five research passes
5. The legacy config.SCHEMES view still exposes what its consumers expect
"""

from __future__ import annotations

import pytest

from src.config import SCHEMES
from src.corpus import load_corpus
from src.corpus.models import DEFAULT_RATE_KEY


# ---------------------------------------------------------------------------
# Loading and shape
# ---------------------------------------------------------------------------

class TestCorpusLoads:
    """The corpus must load and validate, or nothing downstream is trustworthy."""

    def test_corpus_loads(self):
        corpus = load_corpus()
        assert corpus.corpus_version == "v1"
        assert corpus.corporation == "NSFDC"

    def test_five_schemes_present(self):
        """The PS names three products. NSFDC publishes five.

        The PS's own '6.5% to 15% depending on the scheme' is arithmetically
        impossible with three — see docs/data-sources.md §4.1.
        """
        corpus = load_corpus()
        codes = {s.scheme_code for s in corpus.schemes}
        assert codes == {
            "MICRO_FINANCE",
            "TERM_LOAN",
            "AAJEEVIKA_MICRO_FINANCE",
            "UDYAM_NIDHI",
            "EDUCATIONAL_LOAN",
        }

    def test_ps_rate_range_is_reproducible(self):
        """The corpus must span exactly the 6.5%–15% the PS quotes."""
        corpus = load_corpus()
        rates = [r for s in corpus.schemes for r in s.finance.beneficiary_rate_by_partner_type.values()]
        assert min(rates) == 6.5
        assert max(rates) == 15.0

    def test_ps_moratorium_range_is_reproducible(self):
        """The corpus must span the PS's '3 to 12 months'."""
        corpus = load_corpus()
        months = []
        for scheme in corpus.schemes:
            months.append(scheme.finance.moratorium_months)
            months.extend(v.moratorium_months for v in scheme.finance.moratorium_variants)
        assert min(months) == 3
        assert max(months) == 12


# ---------------------------------------------------------------------------
# The guard that matters most
# ---------------------------------------------------------------------------

class TestNoSilentDefaults:
    """Every scheme must declare which project types it serves.

    This is not hypothetical. Project types used to live in a module-level dict
    in schemes.py, and a scheme missing from it matched EVERY project type. The
    moment the corpus grew past three schemes, Udyam Nidhi — a business loan —
    started being offered to education applicants.
    """

    def test_every_scheme_declares_project_types(self):
        corpus = load_corpus()
        for scheme in corpus.schemes:
            assert scheme.project_types, f"{scheme.scheme_code} declares no project_types"

    def test_project_types_are_known_values(self):
        corpus = load_corpus()
        for scheme in corpus.schemes:
            for pt in scheme.project_types:
                assert pt in ("business", "education"), f"{scheme.scheme_code}: bad type {pt!r}"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    """A number without a source is how this project lost five research passes."""

    def test_corpus_has_provenance(self):
        p = load_corpus().provenance
        assert p.source_url.startswith("https://")
        assert p.fetched_at
        assert p.confidence == "OFFICIAL"

    def test_income_ceiling_carries_its_effective_date(self):
        """₹5L rural+urban has an effective date; the ₹3L/₹3.5L figures are stale."""
        shared = load_corpus().shared_eligibility
        assert shared.max_family_income == 500_000
        assert shared.income_effective_date == "2026-01-07"
        assert set(shared.income_applies_to) == {"RURAL", "URBAN"}

    def test_no_age_criterion(self):
        """nsfdc.nic.in states no age condition — its absence is confirmed, not assumed."""
        assert load_corpus().shared_eligibility.age is None


# ---------------------------------------------------------------------------
# Partner-type rate spread — what makes Cheapest Route possible
# ---------------------------------------------------------------------------

class TestPartnerRateSpread:
    """Only Udyam Nidhi publishes a rate that varies by partner category."""

    def test_udyam_nidhi_has_a_spread(self):
        uny = load_corpus().by_code("UDYAM_NIDHI")
        assert uny.finance.has_partner_rate_spread
        assert uny.finance.rate_for_partner_type("COOPERATIVE_BANK") == 13.0
        assert uny.finance.rate_for_partner_type("SMALL_FINANCE_BANK") == 15.0

    def test_other_schemes_have_no_spread(self):
        """Never invent a spread where none is published."""
        corpus = load_corpus()
        for scheme in corpus.schemes:
            if scheme.scheme_code == "UDYAM_NIDHI":
                continue
            assert not scheme.finance.has_partner_rate_spread, scheme.scheme_code
            assert DEFAULT_RATE_KEY in scheme.finance.beneficiary_rate_by_partner_type

    def test_unknown_partner_type_falls_back_to_default(self):
        mfs = load_corpus().by_code("MICRO_FINANCE")
        assert mfs.finance.rate_for_partner_type("SOMETHING_UNSEEN") == 6.5


# ---------------------------------------------------------------------------
# Legacy view — the five existing SCHEMES[...] read sites must keep working
# ---------------------------------------------------------------------------

class TestLegacyView:
    """config.SCHEMES is derived from the corpus but must keep its old shape."""

    def test_legacy_keys_present(self):
        for scheme_id, scheme in SCHEMES.items():
            for key in ("name", "max_project_cost", "financing_pct",
                        "rate_min", "rate_max", "max_income"):
                assert key in scheme, f"{scheme_id} missing legacy key {key}"

    def test_rate_min_equals_rate_max_for_single_rate_schemes(self):
        """This incidentally fixes a real display bug.

        graph.py computes the EMI at rate_min while llm.py quotes rate_max. With
        the old config, Term Loan was rate_min 6.5 / rate_max 15.0 — so the reply
        said "15%" above an EMI calculated at 6.5%. With published rates, the two
        collapse for every scheme except Udyam Nidhi.
        """
        assert SCHEMES["TERM_LOAN"]["rate_min"] == SCHEMES["TERM_LOAN"]["rate_max"] == 8.0
        assert SCHEMES["MICRO_FINANCE"]["rate_min"] == SCHEMES["MICRO_FINANCE"]["rate_max"] == 6.5

    def test_repayment_is_quarterly(self):
        """NSFDC repays quarterly, not monthly — every scheme."""
        for scheme_id, scheme in SCHEMES.items():
            assert scheme["repayment_frequency"] == "QUARTERLY", scheme_id
            assert scheme["periods_per_year"] == 4, scheme_id
