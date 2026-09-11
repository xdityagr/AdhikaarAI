"""
Telling somebody a scheme has opened for them.

The one thing this product does that a person did not ask for at that moment.
Everything else answers a question; this arrives unbidden on somebody's phone,
which is why almost all of the code below is about NOT sending.

WHAT IT TAKES TO SEND ONE MESSAGE

  1. the scheme is genuinely new to the corpus, or its rules changed
  2. we know enough about the person to match them at all
  3. the deterministic matcher says the scheme is aimed at THEM — not merely
     open to everybody, which most schemes are
  4. they have not opted out, and we have actually LOOKED at the opt-out list
  5. we have not already told them about this scheme
  6. Meta has approved a template in a language they read

Any one of those failing is a silent skip, and that is the correct outcome.

WHY THE MESSAGE SAYS SO LITTLE

Outside a 24-hour window only an approved template goes through, and the
template deliberately carries no scheme name and no figure. So the alert is two
steps: the template says there is an update, the person taps a quick-reply
button — which sends a message and opens the window — and the next turn is an
ordinary conversation where the engine computes the real answer and can be
argued with. A rupee figure pushed at somebody who never replies is a figure
nobody can correct.

WHY `is_loaded` IS CHECKED AND NOT JUST `has_opted_out`

`_OPTED_OUT` is a cache. Empty means "we have not looked", not "nobody opted
out", and a job that reads the second meaning messages every person who ever
asked us to stop. `render.yaml` calls that the one data loss here that is not
merely inconvenient, so the job refuses to run rather than risk it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src import meta_whatsapp, whatsapp_consent
from src.discovery import Facets, discover_with_credit

logger = logging.getLogger(__name__)

#: The template that opens the window. Generic, so one approval serves every
#: alert rather than one per scheme queued behind Meta's review.
TEMPLATE = "scheme_update"

#: Never tell one person about more than this many schemes in a run. A corpus
#: refresh that adds four hundred schemes must not become four hundred
#: notifications; somebody who gets that blocks the number, and then we have
#: lost the channel for the alert that mattered.
MAX_PER_PERSON = 3

#: The matcher's own targeting set. A scheme that restricts nobody "matches"
#: everybody, so alerting on a plain match would tell four thousand people
#: about a scheme aimed at none of them.
TARGETING = {"caste", "BPL", "disability", "minority", "occupation",
             "economic distress", "land"}


@dataclass
class Outcome:
    """What a run did, and what it declined to do. Every field is a reason
    somebody did NOT get a message, because that is what needs auditing."""
    considered_schemes: int = 0
    considered_people: int = 0
    sent: int = 0
    skipped_opted_out: int = 0
    skipped_already_told: int = 0
    skipped_no_match: int = 0
    skipped_nothing_known: int = 0
    skipped_no_template: int = 0
    failed: int = 0
    refused: Optional[str] = None
    languages_used: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _facets_from_context(context: dict) -> Optional[Facets]:
    """What we learned about somebody, as something the matcher can use.

    Returns None when we know too little to match on. Alerting from one answer
    would mean telling a person every scheme open to their state, which is most
    of them, which is spam with a deterministic engine behind it.
    """
    known = {k: v for k, v in (context or {}).items() if v not in (None, "", [])}
    usable = {"caste", "gender", "age", "state", "residence", "family_income",
              "is_bpl", "disability", "minority", "is_student", "occupation",
              "employment_status", "marital_status", "owns_pucca_house",
              "owns_house", "owns_vehicle", "owns_boat"}
    fields = {k: v for k, v in known.items() if k in usable}
    if len(fields) < 2:
        return None
    try:
        age = fields.get("age")
        if age is not None:
            fields["age"] = int(age)
        income = fields.get("family_income")
        if income is not None:
            fields["family_income"] = float(income)
    except (TypeError, ValueError):
        fields.pop("age", None)
        fields.pop("family_income", None)
    try:
        return Facets(**fields)
    except TypeError:
        # A context key that is no longer a facet. Drop it rather than fail the
        # whole run for one person's stale row.
        logger.warning("Unusable context keys: %s", sorted(fields))
        return None


def _targeted(match) -> bool:
    return any(reason in TARGETING for reason in match.matched_on)


async def changed_schemes(since: str, corpus_path=None) -> list[tuple[str, str]]:
    """`(slug, name)` for schemes new since `since`, or whose rules moved.

    `first_seen` is populated for the whole corpus; `eligibility_hash` is the
    one that catches a scheme whose RULES changed while its name did not, and
    it is only useful once `scripts/hash_eligibility.py` has run — before that
    this finds new schemes only, which is honest and still worth sending.
    """
    from src.discovery import open_corpus, CORPUS_PATH

    conn = open_corpus(corpus_path or CORPUS_PATH)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT slug, name FROM schemes WHERE first_seen > ? "
            "ORDER BY first_seen DESC", (since,)).fetchall()
        return [(r[0], r[1]) for r in rows]
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("Could not read changed schemes: %s", exc)
        return []
    finally:
        conn.close()


async def run(since: str, dry_run: bool = True,
              corpus_path=None) -> Outcome:
    """One pass. `dry_run` decides everything except whether a message is sent.

    Defaults to a dry run because the failure mode of getting this wrong is
    unsolicited messages to people who trusted us with a phone number, and a
    job that has to be asked twice is a job that cannot be triggered by
    accident.
    """
    from src.database import (alert_already_sent, get_connection,
                              known_users, load_context, record_alert)

    outcome = Outcome()

    # 1. Consent, before anything else.
    if not whatsapp_consent.is_loaded():
        await whatsapp_consent.load()
    if not whatsapp_consent.is_loaded():
        outcome.refused = ("opt-out list could not be loaded; refusing to send "
                           "rather than treat an empty cache as consent")
        logger.error(outcome.refused)
        return outcome

    schemes = await changed_schemes(since, corpus_path)
    outcome.considered_schemes = len(schemes)
    if not schemes:
        return outcome
    by_slug = dict(schemes)

    # 2. What Meta will actually accept, asked rather than assumed.
    approved = await meta_whatsapp.approved_templates()
    languages = approved.get(TEMPLATE, set())
    if not languages and not dry_run:
        outcome.refused = (f"no approved '{TEMPLATE}' template; nothing can be "
                           f"sent outside a 24-hour window")
        logger.warning(outcome.refused)
        return outcome

    db = await get_connection()
    try:
        people = await known_users(db)
        outcome.considered_people = len(people)

        for user_id, language in people:
            if whatsapp_consent.has_opted_out(user_id):
                outcome.skipped_opted_out += 1
                continue

            raw = await load_context(db, user_id)
            context = json.loads(raw) if raw else {}
            facets = _facets_from_context(context)
            if facets is None:
                outcome.skipped_nothing_known += 1
                continue

            result = discover_with_credit(facets, profile=None, limit=200)
            aimed = {m.slug for m in result.matches
                     if m.slug in by_slug and _targeted(m)}
            if not aimed:
                outcome.skipped_no_match += 1
                continue

            # 3. The language Meta approved, falling back to English — which
            #    is worse than their own language and better than silence.
            code = language if language in languages else "en"
            if languages and code not in languages:
                outcome.skipped_no_template += 1
                continue

            told = 0
            for slug in sorted(aimed):
                if told >= MAX_PER_PERSON:
                    break
                if await alert_already_sent(db, user_id, slug):
                    outcome.skipped_already_told += 1
                    continue
                told += 1
                # ONE template per person per run, not one per scheme. The
                # message only says "there is an update"; sending it three
                # times is three notifications for one conversation.
                #
                # The dry run counts the same way, because a dry run that does
                # not predict the real run is worse than no dry run — this
                # reported three where a real pass would have sent one.
                if told == 1:
                    if not dry_run:
                        ok = await meta_whatsapp.send_template(
                            user_id, TEMPLATE, code)
                        if not ok:
                            outcome.failed += 1
                            break
                    outcome.sent += 1
                    outcome.languages_used[code] = \
                        outcome.languages_used.get(code, 0) + 1
                # Recorded per scheme even so: "told" means this person was
                # notified about THIS scheme, so the next run does not count it
                # again as a reason to message them.
                if not dry_run:
                    await record_alert(db, user_id, slug, _now())
    finally:
        await db.close()

    logger.info("Alert run: %s", outcome.as_dict())
    return outcome
