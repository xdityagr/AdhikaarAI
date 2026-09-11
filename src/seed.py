"""
Seed data for channel partners.

Institution names are REAL — these are the actual State Channelizing Agencies
NSFDC lends through. Coordinates are the state capital, which is approximate but
honest for a locator demo (real branch addresses come from the partner-directory
PDFs, which is Phase 2 of the ingest).

Utilisation figures are REAL TOO: they come from NSFDC's published state-wise
allocation-vs-actuals workbook, parsed by src/corpus/ingest.py. So when the
router excludes an agency for being under the 100% norm, that is NSFDC's own
published number doing the excluding, not something we invented.

What remains MOCKED, and is labelled as such everywhere it surfaces:
  - branch-level NPA figures (no public source publishes them)
  - deployable headroom (derived here as a plausible function of allocation)
  - active-overdue flags (internal to NSFDC)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.routing import Partner

logger = logging.getLogger(__name__)

FIXTURE_WORKBOOK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nsfdc_allocation_vs_actuals.xlsx"

# Real SCAs, and the coordinates of the city they operate from.
# Sources: state SC/backward-class development corporation sites; see
# docs/data-sources.md §5.2.
STATE_AGENCIES: list[dict] = [
    {"state": "Uttar Pradesh", "district": "Lucknow", "lat": 26.8467, "lon": 80.9462,
     "name": "UP Scheduled Castes Finance & Development Corporation"},
    {"state": "Maharashtra", "district": "Mumbai", "lat": 19.0760, "lon": 72.8777,
     "name": "Mahatma Phule Backward Class Development Corporation (MPBCDC)"},
    {"state": "Tamil Nadu", "district": "Chennai", "lat": 13.0827, "lon": 80.2707,
     "name": "Tamil Nadu Adi Dravidar Housing & Development Corporation (TAHDCO)"},
    {"state": "West Bengal", "district": "Kolkata", "lat": 22.5726, "lon": 88.3639,
     "name": "West Bengal SC ST Development & Finance Corporation"},
    {"state": "Andhra Pradesh", "district": "Amaravati", "lat": 16.5062, "lon": 80.6480,
     "name": "AP Scheduled Castes Co-operative Finance Corporation"},
    {"state": "Delhi", "district": "New Delhi", "lat": 28.6139, "lon": 77.2090,
     "name": "Delhi SC/ST/OBC/Minorities & Handicapped Finance & Development Corporation"},
    {"state": "Karnataka", "district": "Bengaluru", "lat": 12.9716, "lon": 77.5946,
     "name": "Dr. B.R. Ambedkar Development Corporation, Karnataka"},
    {"state": "Bihar", "district": "Patna", "lat": 25.5941, "lon": 85.1376,
     "name": "Bihar State SC Co-operative Development Corporation"},
    {"state": "Rajasthan", "district": "Jaipur", "lat": 26.9124, "lon": 75.7873,
     "name": "Rajasthan SC/ST Finance & Development Co-operative Corporation"},
    {"state": "Madhya Pradesh", "district": "Bhopal", "lat": 23.2599, "lon": 77.4126,
     "name": "MP Antyavasayi Co-operative Development Corporation"},
    {"state": "Gujarat", "district": "Gandhinagar", "lat": 23.2156, "lon": 72.6369,
     "name": "Gujarat Scheduled Castes Development Corporation"},
    {"state": "Punjab", "district": "Chandigarh", "lat": 30.7333, "lon": 76.7794,
     "name": "Punjab Scheduled Castes Land Development & Finance Corporation"},
]

# A few non-SCA partners so scheme-mandate routing has something to work with.
# Udyam Nidhi runs only through cooperative banks/societies and small finance
# banks, and the rate differs between them — that's the Cheapest Route feature.
OTHER_PARTNERS: list[dict] = [
    {"state": "Uttar Pradesh", "district": "Varanasi", "lat": 25.3176, "lon": 82.9739,
     "name": "Kashi Gomti Samyut Gramin Bank", "agency_type": "RRB", "partner_type": "RRB",
     "net_npa_percentage": 6.4},
    {"state": "Uttar Pradesh", "district": "Ballia", "lat": 25.7585, "lon": 84.1487,
     "name": "Ballia District Co-operative Bank", "agency_type": "OTHER",
     "partner_type": "COOPERATIVE_BANK"},
    {"state": "Uttar Pradesh", "district": "Ballia", "lat": 25.7700, "lon": 84.1400,
     "name": "Utkarsh Small Finance Bank, Ballia", "agency_type": "OTHER",
     "partner_type": "SMALL_FINANCE_BANK"},
    {"state": "Uttar Pradesh", "district": "Ballia", "lat": 25.7450, "lon": 84.1600,
     "name": "Ballia Gramin Sahkari Samiti", "agency_type": "OTHER",
     "partner_type": "COOPERATIVE_SOCIETY"},
    {"state": "Delhi", "district": "New Delhi", "lat": 28.6300, "lon": 77.2200,
     "name": "Delhi Nagrik Sahkari Bank", "agency_type": "OTHER",
     "partner_type": "COOPERATIVE_BANK"},
    {"state": "Maharashtra", "district": "Pune", "lat": 18.5204, "lon": 73.8567,
     "name": "Pune District Central Co-operative Bank", "agency_type": "OTHER",
     "partner_type": "COOPERATIVE_BANK"},
]


def _real_utilisation(financial_year: str = "2025-2026") -> dict[str, tuple[float, float]]:
    """State -> (utilisation fraction, allocation in lakh) from NSFDC's own data.

    Returns an empty mapping if the workbook isn't available, in which case
    callers fall back to a labelled placeholder rather than failing.
    """
    if not FIXTURE_WORKBOOK.exists():
        logger.warning("No utilisation workbook at %s — seeding without real figures",
                       FIXTURE_WORKBOOK)
        return {}
    try:
        from src.corpus.ingest import parse_state_utilisation
        rows = parse_state_utilisation(FIXTURE_WORKBOOK.read_bytes(),
                                       source_url=str(FIXTURE_WORKBOOK))
        return {
            row.state: (row.utilisation_pct / 100.0, row.allocation_lakh)
            for row in rows if row.financial_year == financial_year
        }
    except Exception as exc:
        logger.warning("Could not read utilisation workbook: %s", exc)
        return {}


def seed_partners(financial_year: str = "2025-2026") -> list[Partner]:
    """Build the partner list, with real utilisation wherever NSFDC publishes it."""
    utilisation = _real_utilisation(financial_year)
    partners: list[Partner] = []

    for index, agency in enumerate(STATE_AGENCIES):
        real = utilisation.get(agency["state"])
        if real:
            util, allocation = real
            confidence = "OFFICIAL"
            # Undeployed funds: allocation not yet disbursed. Zero once over 100%.
            headroom = max(0.0, allocation * (1.0 - min(util, 1.0)))
        else:
            util, headroom, confidence = 1.0, 0.0, "MOCKED"

        partners.append(Partner(
            partner_id=f"SCA{index + 1:02d}",
            name=agency["name"],
            agency_type="SCA",
            partner_type="SCA",
            state=agency["state"],
            district=agency["district"],
            latitude=agency["lat"],
            longitude=agency["lon"],
            cumulative_utilization=util,
            has_active_overdues=False,
            deployable_headroom_lakh=round(headroom, 2),
            utilisation_confidence=confidence,
        ))

    for index, entry in enumerate(OTHER_PARTNERS):
        partners.append(Partner(
            partner_id=f"CP{index + 1:02d}",
            name=entry["name"],
            agency_type=entry.get("agency_type", "OTHER"),
            partner_type=entry.get("partner_type", ""),
            state=entry["state"],
            district=entry["district"],
            latitude=entry["lat"],
            longitude=entry["lon"],
            # Non-SCA partners aren't assessed on the utilisation norm.
            cumulative_utilization=None,
            net_npa_percentage=entry.get("net_npa_percentage"),
            deployable_headroom_lakh=0.0,
            npa_confidence="MOCKED",
        ))

    return partners


def partners_near(
    latitude: Optional[float],
    longitude: Optional[float],
    radius_km: float = 150.0,
) -> list[Partner]:
    """Partners within a radius. Everything, when no location is given."""
    everything = seed_partners()
    if latitude is None or longitude is None:
        return everything

    from src.routing import haversine_km
    return [
        p for p in everything
        if p.latitude is not None
        and haversine_km(latitude, longitude, p.latitude, p.longitude) <= radius_km
    ]
