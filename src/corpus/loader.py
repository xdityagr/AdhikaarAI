"""
Corpus loader.

Reads corpus/v<N>/schemes.json, validates it through the Plane A models, and
exposes it to the rest of the app.

Two deliberate constraints, both of which matter more than they look:

1. THE CORPUS PATH IS A MODULE CONSTANT, NOT A SETTINGS FIELD.
   Reading pydantic-settings at import time would construct and cache the
   Settings singleton before any test could patch it, and the test suite mutates
   that singleton. An env override is read straight from os.environ instead.

2. THIS MODULE MUST NOT IMPORT src.config.
   config imports the corpus (to build its legacy SCHEMES view), so the edge has
   to stay one-way or the import cycle is immediate.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from src.corpus.models import Corpus, CorpusError

logger = logging.getLogger(__name__)

# src/corpus/loader.py -> src/corpus -> src -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_VERSION = os.environ.get("YOJNASETU_CORPUS_VERSION", "v1")
CORPUS_DIR = Path(os.environ.get("YOJNASETU_CORPUS_DIR", _PROJECT_ROOT / "corpus"))
SCHEMES_PATH = CORPUS_DIR / CORPUS_VERSION / "schemes.json"


@lru_cache(maxsize=1)
def load_corpus() -> Corpus:
    """Load and validate the scheme corpus. Cached — the corpus is immutable."""
    if not SCHEMES_PATH.exists():
        raise CorpusError(
            f"Scheme corpus not found at {SCHEMES_PATH}. "
            f"Expected corpus/{CORPUS_VERSION}/schemes.json at the project root. "
            f"Note that data/ is gitignored — the corpus lives in corpus/, not data/corpus/."
        )

    try:
        raw = json.loads(SCHEMES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"Scheme corpus at {SCHEMES_PATH} is not valid JSON: {exc}") from exc

    try:
        corpus = Corpus.model_validate(raw)
    except ValidationError as exc:
        # Name the offending fields. A corpus error surfaces at import time and
        # would otherwise present as an opaque traceback across the whole suite.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise CorpusError(f"Scheme corpus at {SCHEMES_PATH} failed validation — {problems}") from exc

    logger.info(
        "Loaded corpus %s: %d schemes from %s",
        corpus.corpus_version,
        len(corpus.schemes),
        corpus.provenance.source_url,
    )
    return corpus


def legacy_schemes_dict() -> dict[str, dict]:
    """The corpus rendered in the shape config.SCHEMES has always had.

    DERIVED — do not edit the result, and do not reintroduce a literal dict.
    Edit corpus/v1/schemes.json instead.

    This exists so the five existing SCHEMES[...] read sites keep working
    unchanged while there is exactly one source of truth behind them.

    Note rate_min/rate_max now collapse to the same value for every scheme that
    publishes a single rate. That incidentally fixes a real display bug: the
    graph computed the EMI at rate_min while the message quoted rate_max, so a
    Term Loan reply said "15%" above an EMI calculated at 6.5%.
    """
    corpus = load_corpus()
    shared = corpus.shared_eligibility

    out: dict[str, dict] = {}
    for scheme in corpus.schemes:
        fin = scheme.finance
        entry: dict = {
            "name": scheme.name,
            "max_project_cost": fin.max_project_cost,
            "min_project_cost": fin.min_project_cost,
            "financing_pct": fin.financing_pct,
            "rate_min": fin.rate_min,
            "rate_max": fin.rate_max,
            "max_income": shared.max_family_income,
            "tenure_months": fin.tenure_months,
            "moratorium_months": fin.moratorium_months,
            "repayment_frequency": fin.repayment_frequency,
            "periods_per_year": fin.periods_per_year,
            "project_types": list(scheme.project_types),
            "max_loan": fin.max_loan,
            "rate_by_partner_type": dict(fin.beneficiary_rate_by_partner_type),
        }
        if fin.women_rebate_pct is not None:
            entry["women_rebate_pct"] = fin.women_rebate_pct
        out[scheme.scheme_code] = entry
    return out
