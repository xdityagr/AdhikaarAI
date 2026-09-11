"""
Aadhaar Paperless Offline e-KYC verification.

This is what separates a recommender from an origination layer. A recommendation
is advice, and a partner has to redo the work. A recommendation attached to
cryptographically verified identity is something a partner can act on.

WHY THIS IS POSSIBLE WITHOUT A LICENCE. Aadhaar *authentication* (the online API)
requires being an AUA/KUA, which needs UIDAI onboarding. Paperless Offline e-KYC
is a different mechanism entirely: the resident downloads their own XML from
UIDAI's site, protected by a share code they choose, and hands it over. The file
is signed by UIDAI. Verifying that signature makes us an Offline Verification
Seeking Entity — no licence, no onboarding, and we never see or store an Aadhaar
number. The reference ID carries only the last four digits.

WHAT THIS PROVES, AND WHAT IT DOESN'T. It proves name, date of birth, gender and
address, signed by UIDAI. It does NOT prove caste or income — those are separate
certificates, and pulling them needs DigiLocker Requester onboarding (PRD-v3 §8,
rung L2). So eligibility here is never gated on verification: an unverified user
gets the same recommendation, graded DECLARED. The ladder degrades, it never
blocks.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

# UIDAI's signing certificate, when configured. Absent by default: it is
# distributed by UIDAI, not bundled here, and pretending to verify without it
# would be worse than saying we can't.
UIDAI_CERT_PATH = Path(__file__).resolve().parents[1] / "corpus" / "uidai_signing_cert.pem"

# A self-signed certificate used ONLY to demonstrate the verification path when
# UIDAI's real certificate isn't installed. It is never treated as UIDAI's: a
# result verified against it is labelled DEMO everywhere it surfaces, so nobody
# can mistake a demonstration for a real identity check. Off unless
# EKYC_DEMO_MODE is set.
DEMO_CERT_PATH = Path(__file__).resolve().parents[1] / "corpus" / "demo_signing_cert.pem"


class ProofGrade(str, Enum):
    """How well established a fact is. Propagates to the eligibility result."""
    VERIFIED = "VERIFIED"    # cryptographically or legally established
    DECLARED = "DECLARED"    # user-stated, good faith, unverified
    INFERRED = "INFERRED"    # derived from other fields


@dataclass
class OfflineKyc:
    """Demographics from a UIDAI offline e-KYC XML.

    Deliberately no Aadhaar number field — the XML doesn't contain one, and this
    type exists partly to make that impossible to add by accident.
    """
    name: str = ""
    date_of_birth: str = ""
    gender: str = ""
    care_of: str = ""
    district: str = ""
    state: str = ""
    pincode: str = ""
    village_town_city: str = ""
    reference_id: str = ""
    generated_at: str = ""

    @property
    def aadhaar_last4(self) -> str:
        """UIDAI puts the last four digits at the front of the reference ID."""
        return self.reference_id[:4] if len(self.reference_id) >= 4 else ""

    @property
    def normalised_gender(self) -> str:
        return {"M": "male", "F": "female", "T": "other"}.get(
            (self.gender or "").upper()[:1], "other")


@dataclass
class VerificationResult:
    grade: ProofGrade = ProofGrade.DECLARED
    kyc: Optional[OfflineKyc] = None
    signature_valid: bool = False
    is_demo: bool = False    # verified against the demo cert, not UIDAI's
    reason: str = ""
    checks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.grade is ProofGrade.VERIFIED


class VerificationError(Exception):
    """The file could not be opened or parsed. Never raised for a bad signature —
    an unverifiable file is a DECLARED result, not an error."""


# ---------------------------------------------------------------------------
# Opening the archive
# ---------------------------------------------------------------------------

def open_offline_ekyc(zip_bytes: bytes, share_code: str) -> bytes:
    """Extract the XML from a UIDAI offline e-KYC ZIP.

    The share code is chosen by the resident when they generate the file, and is
    the ZIP password. We never persist it.
    """
    if not share_code:
        raise VerificationError("A share code is required to open this file.")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise VerificationError("No XML found inside the archive.")
            return archive.read(names[0], pwd=share_code.encode("utf-8"))
    except RuntimeError as exc:
        # zipfile raises RuntimeError("Bad password ...") for a wrong share code.
        if "password" in str(exc).lower():
            raise VerificationError("That share code didn't open the file.") from exc
        raise VerificationError(f"Could not read the archive: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise VerificationError("That file isn't a valid Aadhaar offline e-KYC ZIP.") from exc


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_offline_ekyc(xml_bytes: bytes) -> OfflineKyc:
    """Read demographics out of the offline e-KYC XML."""
    from lxml import etree

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise VerificationError(f"The e-KYC XML is malformed: {exc}") from exc

    poi = root.find(".//Poi")
    poa = root.find(".//Poa")
    if poi is None:
        raise VerificationError("The XML has no Poi block — this isn't an offline e-KYC file.")

    get = lambda node, attr: (node.get(attr) or "").strip() if node is not None else ""

    return OfflineKyc(
        name=get(poi, "name"),
        date_of_birth=get(poi, "dob"),
        gender=get(poi, "gender"),
        care_of=get(poa, "careof"),
        district=get(poa, "dist"),
        state=get(poa, "state"),
        pincode=get(poa, "pc"),
        village_town_city=get(poa, "vtc"),
        reference_id=(root.get("referenceId") or "").strip(),
        generated_at=(root.get("generatedDate") or "").strip(),
    )


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------

def verify_xml_signature(xml_bytes: bytes, cert_pem: bytes) -> tuple[bool, str]:
    """Verify the enveloped XMLDSig on a UIDAI e-KYC document.

    Standard enveloped-signature verification, done by hand because signxml
    isn't a dependency and this is only ~40 lines:

      1. lift out SignedInfo and the SignatureValue
      2. remove the Signature element to recover what was actually digested
      3. canonicalise (C14N) and SHA-256 the document, compare to DigestValue
      4. canonicalise SignedInfo and RSA-verify SignatureValue over it

    Both steps matter. Checking only the RSA signature would let someone swap the
    document body; checking only the digest would let them forge it outright.
    """
    from lxml import etree
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.x509 import load_pem_x509_certificate

    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser=parser)

        signature = root.find(f".//{{{DSIG_NS}}}Signature")
        if signature is None:
            return False, "The file carries no UIDAI signature."

        signed_info = signature.find(f"{{{DSIG_NS}}}SignedInfo")
        sig_value_el = signature.find(f"{{{DSIG_NS}}}SignatureValue")
        digest_el = signature.find(f".//{{{DSIG_NS}}}DigestValue")
        if signed_info is None or sig_value_el is None or digest_el is None:
            return False, "The signature block is incomplete."

        import base64
        signature_value = base64.b64decode((sig_value_el.text or "").strip())
        expected_digest = base64.b64decode((digest_el.text or "").strip())

        # (2) Enveloped transform: the digest was taken over the document with
        # the Signature element removed.
        body = etree.fromstring(xml_bytes, parser=parser)
        body_sig = body.find(f".//{{{DSIG_NS}}}Signature")
        if body_sig is not None:
            body_sig.getparent().remove(body_sig)

        # (3) Digest check.
        canonical_body = etree.tostring(body, method="c14n", exclusive=False, with_comments=False)
        hasher = hashes.Hash(hashes.SHA256())
        hasher.update(canonical_body)
        if hasher.finalize() != expected_digest:
            return False, "The document doesn't match its signed digest — it has been altered."

        # (4) Signature check over SignedInfo.
        canonical_signed_info = etree.tostring(
            signed_info, method="c14n", exclusive=False, with_comments=False)
        public_key = load_pem_x509_certificate(cert_pem).public_key()
        public_key.verify(
            signature_value, canonical_signed_info,
            padding.PKCS1v15(), hashes.SHA256(),
        )
        return True, "Signature verified against the UIDAI certificate."

    except Exception as exc:  # invalid signature, bad cert, malformed input
        logger.info("e-KYC signature did not verify: %s: %s", type(exc).__name__, exc)
        return False, "The signature did not verify against the UIDAI certificate."


def _load_cert(cert_pem: Optional[bytes]) -> tuple[Optional[bytes], bool]:
    """Return (certificate, is_demo). The real one always wins."""
    if cert_pem:
        return cert_pem, False
    if UIDAI_CERT_PATH.exists():
        return UIDAI_CERT_PATH.read_bytes(), False

    import os
    demo_enabled = os.environ.get("EKYC_DEMO_MODE", "").lower() in ("1", "true", "yes")
    if demo_enabled and DEMO_CERT_PATH.exists():
        return DEMO_CERT_PATH.read_bytes(), True
    return None, False


# ---------------------------------------------------------------------------
# The one call the rest of the app makes
# ---------------------------------------------------------------------------

def verify_offline_ekyc(
    zip_bytes: bytes,
    share_code: str,
    cert_pem: Optional[bytes] = None,
) -> VerificationResult:
    """Open, parse and verify an offline e-KYC file.

    Returns a graded result rather than raising on an unverifiable signature:
    a DECLARED result is a legitimate outcome and the user still gets their full
    recommendation. Only an unreadable file raises.
    """
    xml_bytes = open_offline_ekyc(zip_bytes, share_code)
    kyc = parse_offline_ekyc(xml_bytes)

    result = VerificationResult(kyc=kyc)
    result.checks.append("Archive opened with the share code")
    result.checks.append("Demographics parsed")

    cert, is_demo = _load_cert(cert_pem)
    if cert is None:
        result.grade = ProofGrade.DECLARED
        result.reason = (
            "Details read from the file, but UIDAI's signing certificate isn't "
            "configured on this server, so the signature could not be checked."
        )
        return result

    valid, reason = verify_xml_signature(xml_bytes, cert)
    result.signature_valid = valid
    result.is_demo = is_demo
    result.grade = ProofGrade.VERIFIED if valid else ProofGrade.DECLARED
    result.reason = (
        reason.replace("the UIDAI certificate", "a DEMONSTRATION certificate")
        if is_demo else reason
    )
    if valid:
        result.checks.append(
            "Signature verified against a DEMONSTRATION certificate, not UIDAI's"
            if is_demo else "UIDAI signature verified"
        )
        result.checks.append("Document digest matches — contents unaltered")
    return result


def describe(result: VerificationResult) -> str:
    """One line for a user, in the same register as the rest of the copy."""
    if result.ok and result.kyc:
        if result.is_demo:
            return (
                f"*Identity verified (DEMONSTRATION)* — {result.kyc.name}, "
                f"Aadhaar ending {result.kyc.aadhaar_last4}. "
                f"The signature checks out, but against a demonstration certificate — "
                f"not UIDAI's. On a real file this is the same check."
            )
        return (
            f"*Identity verified* — {result.kyc.name}, "
            f"Aadhaar ending {result.kyc.aadhaar_last4}. "
            f"Checked against UIDAI's own digital signature. "
            f"Your Aadhaar number was never shared with us."
        )
    return (
        "*Identity not verified* — "
        + (result.reason or "the file could not be checked.")
        + " You'll still get your full recommendation; it's marked as self-declared."
    )
