"""
Scheme corpus — the single source of truth for scheme numbers.

Plane A only (typed, deterministic). See docs/data-sources.md §2.2.

Import edge is one-way: config imports corpus, corpus never imports config.
"""

from src.corpus.loader import (
    CORPUS_DIR,
    CORPUS_VERSION,
    SCHEMES_PATH,
    legacy_schemes_dict,
    load_corpus,
)
from src.corpus.models import (
    DEFAULT_RATE_KEY,
    PERIODS_PER_YEAR,
    Corpus,
    CorpusError,
    Scheme,
    SchemeFinance,
    SchemeRouting,
)

__all__ = [
    "CORPUS_DIR",
    "CORPUS_VERSION",
    "SCHEMES_PATH",
    "DEFAULT_RATE_KEY",
    "PERIODS_PER_YEAR",
    "Corpus",
    "CorpusError",
    "Scheme",
    "SchemeFinance",
    "SchemeRouting",
    "legacy_schemes_dict",
    "load_corpus",
]
