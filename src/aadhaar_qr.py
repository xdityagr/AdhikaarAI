"""
Reading the Secure QR printed on an Aadhaar card.

THE POINT

Filling eleven fields on a phone keyboard, often in a script the on-screen
keyboard makes hard, is the biggest drop-off in this product. UIDAI's offline
e-KYC file would avoid it but costs about seven steps and an OTP on their
website, which is worse. The QR already printed on the card costs three: tap,
allow the camera, point it at the card.

WHAT THE QR ACTUALLY IS

Not a URL and not JSON. The scanner returns one very long decimal number, and
the data is inside it:

    decimal string -> big integer -> bytes -> gzip -> 0xFF-delimited fields

The tail is not text. After the delimited fields come the holder's photograph,
then optionally a SHA-256 hash of their mobile and email, and the LAST 256
BYTES ARE AN RSA SIGNATURE over everything before them, made by UIDAI.

WHY THIS IS ALLOWED WITHOUT A LICENCE

Same footing as the offline e-KYC XML this codebase already verifies. The
resident presents their own card; we read what is printed on it. That makes us
an Offline Verification Seeking Entity — no UIDAI onboarding, no AUA/KUA.

Aadhaar *authentication* (the online API) is the thing that needs a licence,
and we do not touch it.

WHAT IS AND IS NOT IN HERE

There is no full Aadhaar number in the QR, so there is none in this module and
none in the type it returns. UIDAI puts only the last four digits at the front
of the reference id. We use them to show "…1234" so someone can tell which card
they scanned, and we store nothing.

The photograph is deliberately discarded. It is the most identifying thing in
the payload, we have no use for it, and the safest place for data you do not
need is nowhere.

WHAT A SIGNATURE PROVES

That UIDAI issued this name, date of birth, gender and address, and that
nobody has altered them. It does NOT prove caste or income — those are separate
certificates — so eligibility is never gated on it. An unverified person gets
exactly the same answer, graded DECLARED. The ladder degrades; it never blocks.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# UIDAI separates the text fields with byte 255.
DELIMITER = 255

# RSA-2048 over SHA-256: the trailing 256 bytes of the payload.
SIGNATURE_BYTES = 256

# Field order in the V2 Secure QR, as published by UIDAI. Index 0 is a digit
# saying whether a mobile and/or email hash is appended after the photograph.
FIELD_ORDER = [
    "email_mobile_present",
    "reference_id",
    "name",
    "dob",
    "gender",
    "care_of",
    "district",
    "landmark",
    "house",
    "location",
    "pincode",
    "post_office",
    "state",
    "street",
    "sub_district",
    "vtc",
]

# Where UIDAI's production signing certificate is looked for. Absent, the data
# is still parsed and returned — clearly marked unverified — because a missing
# certificate is our problem and should not stop someone filling a form.
CERT_PATHS = (
    Path("corpus/uidai_auth_prod.cer"),
    Path("corpus/uidai_auth_prod.pem"),
)


class AadhaarQrError(Exception):
    """The QR could not be read as an Aadhaar Secure QR."""


@dataclass
class ScannedAadhaar:
    name: str = ""
    dob: str = ""
    gender: str = ""
    care_of: str = ""
    house: str = ""
    street: str = ""
    landmark: str = ""
    location: str = ""
    vtc: str = ""
    post_office: str = ""
    sub_district: str = ""
    district: str = ""
    state: str = ""
    pincode: str = ""
    reference_id: str = ""
    """True only when UIDAI's signature checked out against their certificate."""
    verified: bool = False
    """Why it did not verify, when it did not. Shown to nobody but the logs."""
    verify_note: str = ""
    """Every text field, exactly as the card wrote it.

    Kept so that "it did not fill my date of birth" can be answered with what
    the card actually says rather than with a theory. Returned to the person
    who scanned their own card and stored nowhere — it is the same data as the
    fields above, differently arranged."""
    raw_fields: dict = field(default_factory=dict)

    @property
    def aadhaar_last4(self) -> str:
        """The only part of the number that exists in the payload at all."""
        return self.reference_id[:4] if len(self.reference_id) >= 4 else ""

    @property
    def normalised_gender(self) -> str:
        return {"M": "male", "F": "female", "T": "other"}.get(
            (self.gender or "").upper()[:1], "")

    @property
    def address(self) -> str:
        """One line, in the order an Indian address is written and spoken."""
        parts = [self.house, self.street, self.landmark, self.location,
                 self.vtc, self.post_office, self.sub_district]
        seen, ordered = set(), []
        for part in parts:
            cleaned = (part or "").strip().strip(",")
            # UIDAI repeats the village in both `location` and `vtc` often
            # enough that an address reading "Rampur, Rampur" is the norm
            # rather than the exception.
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                ordered.append(cleaned)
        return ", ".join(ordered)


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def _to_bytes(qr_text: str) -> bytes:
    """The scanner's decimal string, as the bytes it stands for."""
    digits = "".join(ch for ch in (qr_text or "") if ch.isdigit())
    if not digits:
        raise AadhaarQrError("not an Aadhaar Secure QR (no digits)")
    if len(digits) < 200:
        # A pre-2018 letter carries a short plaintext QR with almost nothing in
        # it. Saying so beats failing with a decompression error.
        raise AadhaarQrError("this looks like an older Aadhaar QR, which does "
                             "not carry these details")
    value = int(digits)
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def _decompress(raw: bytes) -> bytes:
    """Gzip, with a raw-deflate fallback.

    Cards issued across different years are not consistent about the wrapper,
    and a header difference must not read as an unreadable card.
    """
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError as exc:
            raise AadhaarQrError(f"could not decompress: {exc}") from exc
    for wbits in (zlib.MAX_WBITS | 32, -zlib.MAX_WBITS):
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    # Some cards are not compressed at all.
    if DELIMITER in raw:
        return raw
    raise AadhaarQrError("could not decompress the QR payload")


#: Cards issued from about 2022 begin with a version marker — "V2", "V3" — and
#: older ones go straight into the email/mobile indicator. One extra field at
#: the front shifts EVERY later field by one, which does not fail: it fills the
#: form with the neighbouring value. A real card read back a reference id as
#: the person's name and the gender as their father's name.
_VERSION_MARKER = re.compile(rb"^V\d+$", re.IGNORECASE)

#: The reference id is the last four Aadhaar digits followed by a timestamp, so
#: it is long and entirely numeric — the one field whose shape identifies it,
#: and therefore the anchor everything else is measured from.
_REFERENCE_ID = re.compile(rb"^\d{12,}$")


def _leading_offset(parts: list[bytes]) -> int:
    """How many fields sit in front of the email/mobile indicator.

    Detected rather than assumed, because both layouts are in circulation and
    a wrong guess is silent: it produces a filled form full of the wrong
    answers, which is worse than an empty one.
    """
    # The anchor, when we can see it: the reference id sits immediately after
    # the indicator, so its position tells us the whole layout.
    for index, part in enumerate(parts[:4]):
        if _REFERENCE_ID.match(part.strip()):
            return max(0, index - 1)
    # No anchor visible; fall back to looking for the version marker itself.
    if parts and _VERSION_MARKER.match(parts[0].strip()):
        return 1
    return 0


def _split_fields(data: bytes) -> tuple[dict[str, str], bytes]:
    """The delimited text fields, and everything after them.

    Only the leading text fields are characters. What follows is the
    photograph and the signature, which must never be decoded as text.
    """
    # One more than we need, so the offset can be detected before anything is
    # assigned to a name.
    probe = data.split(bytes([DELIMITER]), len(FIELD_ORDER) + 2)
    offset = _leading_offset(probe)

    fields: dict[str, str] = {}
    start = 0
    # Skip whatever sits in front of the indicator.
    for _ in range(offset):
        start = data.find(bytes([DELIMITER]), start) + 1
        if start <= 0:
            raise AadhaarQrError("the QR ended early — no fields found")

    for index, key in enumerate(FIELD_ORDER):
        end = data.find(bytes([DELIMITER]), start)
        if end < 0:
            raise AadhaarQrError(
                f"the QR ended early — only {index} of {len(FIELD_ORDER)} fields")
        fields[key] = data[start:end].decode("utf-8", errors="replace").strip()
        start = end + 1

    # Last line of defence. If the reference id did not land on the reference
    # id, the mapping is wrong and every value below it is somebody else's
    # field — better to refuse than to fill a government form with it.
    reference = fields.get("reference_id", "")
    if reference and not reference.isdigit():
        raise AadhaarQrError(
            "this card's fields are not in an order we recognise — "
            "please type the details instead")

    return fields, data[start:]


def _verify(signed: bytes, signature: bytes, cert_pem: Optional[bytes]) -> tuple[bool, str]:
    """Check UIDAI's RSA signature over everything before the last 256 bytes."""
    if not cert_pem:
        return False, "no UIDAI certificate available"
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_der_x509_certificate, load_pem_x509_certificate

        loader = (load_pem_x509_certificate
                  if cert_pem.lstrip().startswith(b"-----")
                  else load_der_x509_certificate)
        public_key = loader(cert_pem).public_key()
        public_key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        return True, "signed by UIDAI"
    except Exception as exc:                                  # noqa: BLE001
        return False, f"signature did not verify: {type(exc).__name__}"


def _load_cert() -> Optional[bytes]:
    for path in CERT_PATHS:
        if path.exists():
            try:
                return path.read_bytes()
            except OSError:
                continue
    return None


def scan(qr_text: str, cert_pem: Optional[bytes] = None) -> ScannedAadhaar:
    """One scanned Aadhaar Secure QR, as demographics.

    Raises `AadhaarQrError` when the payload is not an Aadhaar Secure QR at
    all. A payload that parses but does not verify is RETURNED, marked
    unverified — the person is trying to fill in a form, and refusing to help
    them because we could not load a certificate would punish them for our
    own missing file.
    """
    data = _decompress(_to_bytes(qr_text))
    fields, tail = _split_fields(data)

    verified, note = False, "payload too short to be signed"
    if len(tail) > SIGNATURE_BYTES:
        signature = tail[-SIGNATURE_BYTES:]
        # The signature covers everything before it, including the photograph.
        signed = data[: len(data) - SIGNATURE_BYTES]
        verified, note = _verify(signed, signature, cert_pem or _load_cert())

    scanned = ScannedAadhaar(
        name=fields.get("name", ""),
        dob=fields.get("dob", ""),
        gender=fields.get("gender", ""),
        care_of=fields.get("care_of", ""),
        house=fields.get("house", ""),
        street=fields.get("street", ""),
        landmark=fields.get("landmark", ""),
        location=fields.get("location", ""),
        vtc=fields.get("vtc", ""),
        post_office=fields.get("post_office", ""),
        sub_district=fields.get("sub_district", ""),
        district=fields.get("district", ""),
        state=fields.get("state", ""),
        pincode=fields.get("pincode", ""),
        reference_id=fields.get("reference_id", ""),
        verified=verified,
        verify_note=note,
        raw_fields=dict(fields),
    )
    logger.info("Scanned an Aadhaar QR (verified=%s, %s)", verified, note)
    return scanned


#: S/O, D/O, W/O, C/O — son, daughter, wife or care of. Cards vary in
#: case and in what follows the marker, so both are matched loosely.
_CARE_OF_PREFIX = re.compile(r"^\s*[SDWC]\s*/\s*O\b[\s:.,\-]*", re.IGNORECASE)


def to_profile(scanned: ScannedAadhaar) -> dict:
    """The scan, in the shape the application pack and the profile sheet use.

    Empty values are omitted rather than sent as "", so a field the card did
    not carry stays genuinely blank on the printed form instead of looking
    answered.
    """
    candidate = {
        "full_name": scanned.name,
        # "S/O Manish Kumar Gaur" is a relationship marker plus a name, and the
        # form wants the name. Case-insensitive and tolerant of the separator
        # because cards are not consistent: S/O, s/o, "S/O:", "C/O -" all
        # occur, and a literal replace left the lowercase ones showing "s/o"
        # in a field labelled "father's name".
        "parent_name": _CARE_OF_PREFIX.sub("", scanned.care_of).strip(" :,-"),
        "dob": scanned.dob,
        "gender": scanned.normalised_gender,
        "address": scanned.address,
        "district": scanned.district,
        "state": scanned.state,
        "pincode": scanned.pincode,
        "proof": "verified" if scanned.verified else "declared",
    }
    return {k: v for k, v in candidate.items() if v}


def dob_to_iso(dob: str) -> str:
    """UIDAI writes DD-MM-YYYY; an <input type="date"> wants YYYY-MM-DD."""
    parts = (dob or "").replace("/", "-").split("-")
    if len(parts) == 3 and len(parts[0]) == 2 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return dob or ""


def fingerprint(qr_text: str) -> str:
    """A short, non-reversible id for logs, so a scan can be traced without
    the payload itself ever being written down."""
    return hashlib.sha256((qr_text or "").encode()).hexdigest()[:12]
