"""
Shared test fixtures.

Before this file existed, each DB-touching test module rolled its own temp-database
setup, and the two implementations disagreed:

- test_phase0.py patched src.database.get_settings (correct, but local)
- test_cache.py and test_llm.py MUTATED the @lru_cache'd Settings singleton and
  never restored it, so whatever they set leaked into every module and every test
  that ran afterwards. That made the suite order-dependent — a latent bug that
  had not bitten yet only because the leaked value happened to be harmless.
- test_buttons.py used no fixture at all and wrote a real data/adhikaar.db.

The autouse fixture below gives every test its own throwaway database and puts the
singleton back the way it found it. Mutating the cached Settings object inside a
test is still fine — it just no longer escapes the test that did it.
"""

from __future__ import annotations

import pytest

from src.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    """Point the database at a per-test temp file; restore all mutations after.

    Autouse so no test can forget it. Snapshots the whole Settings field set
    rather than just database_path, because test_llm.py also mutates
    gemini_api_key and the same leak applies.
    """
    settings = get_settings()
    snapshot = {name: getattr(settings, name) for name in type(settings).model_fields}

    settings.database_path = str(tmp_path / "test.db")

    yield settings

    for name, value in snapshot.items():
        setattr(settings, name, value)
    # The Settings object is cached; clearing it means a later import-time read
    # can't observe a value some test left behind.
    get_settings.cache_clear()
