"""
Turning where someone is into a state, a district and a PIN code.

Scheme eligibility is overwhelmingly state-scoped, so the single most valuable
thing we can learn without asking a question is which state the person is
standing in. The previous build asked them to pick from five hardcoded cities,
which is not a location feature — it is a dropdown that excludes 99% of India.

Three routes in, in order of how little they ask of the person:

1. **Browser geolocation** — one tap, no typing. Coordinates are reverse
   geocoded through us, not from their browser, so the lookup carries our
   identifying User-Agent and one shared cache rather than their IP hitting a
   public service directly.
2. **PIN code** — six digits, which people know by heart and can read off any
   letter. Resolved against India Post's own directory.
3. **Pick a state** — always available, needs no network and no permission.

Every lookup is cached on disk. These directories change on the order of years,
a demo should not depend on a third party being up, and both services are free
public goods that deserve to be asked once rather than once per user.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

from src.paths import GEO_CACHE_DB as CACHE_PATH

# Both services ask that automated callers identify themselves. Nominatim's
# usage policy in particular requires a real contact address, and being a good
# citizen of a free service is the price of using it.
USER_AGENT = (
    "YojnaSetu/0.1 (government scheme access for marginalised households; "
    "+https://github.com/xdityagr/AdhikaarAI)"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
POSTAL_URL = "https://api.postalpincode.in/pincode/{pin}"

TIMEOUT = httpx.Timeout(6.0, connect=4.0)

# Coordinates are rounded before lookup and before caching. Three decimals is
# about 110 m — far finer than a district boundary, and it means we never store
# a precise fix on where a person was standing.
COORD_PRECISION = 3


@dataclass
class Place:
    state: Optional[str] = None
    district: Optional[str] = None
    pin: Optional[str] = None
    source: str = "unknown"
    matched: bool = field(default=False)

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "district": self.district,
            "pin": self.pin,
            "source": self.source,
            "matched": self.matched,
        }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS geo_cache (
               key TEXT PRIMARY KEY,
               payload TEXT NOT NULL,
               cached_at REAL NOT NULL
           )"""
    )
    return conn


def _cached(key: str) -> Optional[Place]:
    try:
        conn = _connect()
    except sqlite3.Error as exc:
        logger.warning("Geo cache unavailable: %s", exc)
        return None
    try:
        row = conn.execute(
            "SELECT payload FROM geo_cache WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    data = json.loads(row[0])
    return Place(**data)


def _store(key: str, place: Place) -> None:
    try:
        conn = _connect()
    except sqlite3.Error:
        return
    try:
        conn.execute(
            "INSERT OR REPLACE INTO geo_cache (key, payload, cached_at) VALUES (?,?,?)",
            (key, json.dumps(place.as_dict()), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# State names
# ---------------------------------------------------------------------------

# The corpus spells states one exact way, and a scheme filtered on a name that
# does not match returns nothing at all. These are the spellings that differ
# between OSM/India Post and myScheme.
_STATE_ALIASES = {
    "nct of delhi": "Delhi",
    "national capital territory of delhi": "Delhi",
    "delhi": "Delhi",
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "jammu and kashmir": "Jammu and Kashmir",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
}


def canonical_state(name: Optional[str],
                    known: Optional[set[str]] = None) -> Optional[str]:
    """Map a state name onto the spelling the corpus uses.

    Returns the input unchanged when we have no better answer: a name we fail to
    recognise is far better passed through — it may simply be correct — than
    dropped, which would silently widen the search to the whole country.
    """
    if not name:
        return None
    cleaned = " ".join(name.strip().split())
    alias = _STATE_ALIASES.get(cleaned.lower())
    if alias:
        cleaned = alias
    if known:
        for candidate in known:
            if candidate.lower() == cleaned.lower():
                return candidate
    return cleaned


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

async def reverse_geocode(lat: float, lon: float) -> Place:
    """Coordinates to state and district, via OpenStreetMap."""
    key = f"rev:{round(lat, COORD_PRECISION)},{round(lon, COORD_PRECISION)}"
    hit = _cached(key)
    if hit is not None:
        return hit

    place = Place(source="geolocation")
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "lat": round(lat, COORD_PRECISION),
                    "lon": round(lon, COORD_PRECISION),
                    "format": "jsonv2",
                    "zoom": 10,          # district level; finer is wasted detail
                    "addressdetails": 1,
                },
            )
            response.raise_for_status()
            address = response.json().get("address", {})
    except (httpx.HTTPError, ValueError) as exc:
        # A failed lookup must not block the person. They fall through to the
        # PIN box, which is why it is always on screen.
        logger.warning("Reverse geocode failed: %s", exc)
        return place

    place.state = canonical_state(address.get("state"))
    place.district = (
        address.get("state_district")
        or address.get("district")
        or address.get("county")
    )
    place.pin = address.get("postcode")
    place.matched = bool(place.state)
    if place.matched:
        _store(key, place)
    return place


async def lookup_pin(pin: str) -> Place:
    """Six digits to state and district, via India Post."""
    pin = "".join(ch for ch in pin if ch.isdigit())
    place = Place(pin=pin or None, source="pin")
    if len(pin) != 6:
        return place

    hit = _cached(f"pin:{pin}")
    if hit is not None:
        return hit

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(POSTAL_URL.format(pin=pin))
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("PIN lookup failed for %s: %s", pin, exc)
        return place

    # The API answers with a single-element list whose Status is a string.
    entry = payload[0] if isinstance(payload, list) and payload else {}
    offices = entry.get("PostOffice") or []
    if entry.get("Status") != "Success" or not offices:
        return place

    office = offices[0]
    place.state = canonical_state(office.get("State"))
    place.district = office.get("District")
    place.matched = bool(place.state)
    if place.matched:
        _store(f"pin:{pin}", place)
    return place
