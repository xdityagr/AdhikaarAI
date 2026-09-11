"""
Aadhaar Paperless Offline e-KYC verification tests.

These build a genuinely signed document with a real RSA key and verify it, so
the cryptography is actually exercised rather than mocked. The tampering tests
matter most: a verifier that accepts an altered document is worse than no
verifier, because it launders a forgery into a VERIFIED badge.
"""

from __future__ import annotations

import base64
import io
import zipfile

import pytest

from src.verification import (
    DSIG_NS,
    OfflineKyc,
    ProofGrade,
    VerificationError,
    describe,
    open_offline_ekyc,
    parse_offline_ekyc,
    verify_offline_ekyc,
    verify_xml_signature,
)


# ---------------------------------------------------------------------------
# Fixture builder — a real signed document
# ---------------------------------------------------------------------------

def _keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _self_signed_cert(key) -> bytes:
    """Stands in for UIDAI's signing certificate."""
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Offline eKYC Signer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def _signed_ekyc_xml(key, name="Sunita Devi", dob="14-06-1991", gender="F") -> bytes:
    """Build an offline e-KYC XML with a valid enveloped XMLDSig."""
    from lxml import etree
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    root = etree.Element("OfflinePaperlessKyc",
                         referenceId="8123202609041530", generatedDate="2026-09-04")
    uid = etree.SubElement(root, "UidData")
    etree.SubElement(uid, "Poi", name=name, dob=dob, gender=gender)
    etree.SubElement(uid, "Poa", careof="C/O Ram Devi", dist="Ballia",
                     state="Uttar Pradesh", pc="277001", vtc="Ballia")

    # Digest over the document as it stands, before the Signature is added —
    # which is exactly what the verifier reconstructs by removing it.
    body = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)
    hasher = hashes.Hash(hashes.SHA256())
    hasher.update(body)
    digest = base64.b64encode(hasher.finalize()).decode()

    sig = etree.SubElement(root, f"{{{DSIG_NS}}}Signature")
    signed_info = etree.SubElement(sig, f"{{{DSIG_NS}}}SignedInfo")
    etree.SubElement(signed_info, f"{{{DSIG_NS}}}CanonicalizationMethod",
                     Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    etree.SubElement(signed_info, f"{{{DSIG_NS}}}SignatureMethod",
                     Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")
    ref = etree.SubElement(signed_info, f"{{{DSIG_NS}}}Reference", URI="")
    transforms = etree.SubElement(ref, f"{{{DSIG_NS}}}Transforms")
    etree.SubElement(transforms, f"{{{DSIG_NS}}}Transform",
                     Algorithm=f"{DSIG_NS}enveloped-signature")
    etree.SubElement(ref, f"{{{DSIG_NS}}}DigestMethod",
                     Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
    etree.SubElement(ref, f"{{{DSIG_NS}}}DigestValue").text = digest

    canonical_signed_info = etree.tostring(
        signed_info, method="c14n", exclusive=False, with_comments=False)
    signature_value = key.sign(canonical_signed_info, padding.PKCS1v15(), hashes.SHA256())
    etree.SubElement(sig, f"{{{DSIG_NS}}}SignatureValue").text = \
        base64.b64encode(signature_value).decode()

    return etree.tostring(root)


def _zip_with(xml_bytes: bytes, filename="offline_ekyc.xml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, xml_bytes)
    return buf.getvalue()


@pytest.fixture(scope="module")
def signed():
    key = _keypair()
    return {"key": key, "cert": _self_signed_cert(key), "xml": _signed_ekyc_xml(key)}


# ---------------------------------------------------------------------------
# Archive handling
# ---------------------------------------------------------------------------

class TestArchive:
    def test_extracts_the_xml(self, signed):
        assert b"OfflinePaperlessKyc" in open_offline_ekyc(_zip_with(signed["xml"]), "1234")

    def test_missing_share_code_is_rejected(self, signed):
        with pytest.raises(VerificationError, match="share code"):
            open_offline_ekyc(_zip_with(signed["xml"]), "")

    def test_not_a_zip(self):
        with pytest.raises(VerificationError, match="valid Aadhaar offline"):
            open_offline_ekyc(b"this is not a zip file", "1234")

    def test_zip_without_xml(self):
        with pytest.raises(VerificationError, match="No XML"):
            open_offline_ekyc(_zip_with(b"nope", filename="readme.txt"), "1234")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParsing:
    def test_reads_demographics(self, signed):
        kyc = parse_offline_ekyc(signed["xml"])
        assert kyc.name == "Sunita Devi"
        assert kyc.date_of_birth == "14-06-1991"
        assert kyc.district == "Ballia"
        assert kyc.state == "Uttar Pradesh"
        assert kyc.pincode == "277001"

    def test_only_the_last_four_aadhaar_digits_are_present(self, signed):
        """The XML carries no Aadhaar number, and neither do we."""
        kyc = parse_offline_ekyc(signed["xml"])
        assert kyc.aadhaar_last4 == "8123"
        assert not hasattr(kyc, "aadhaar_number")

    def test_gender_normalises_to_the_profile_vocabulary(self):
        assert OfflineKyc(gender="F").normalised_gender == "female"
        assert OfflineKyc(gender="M").normalised_gender == "male"
        assert OfflineKyc(gender="T").normalised_gender == "other"

    def test_malformed_xml_is_rejected(self):
        with pytest.raises(VerificationError, match="malformed"):
            parse_offline_ekyc(b"<OfflinePaperlessKyc><unclosed>")

    def test_wrong_document_shape_is_rejected(self):
        with pytest.raises(VerificationError, match="isn't an offline e-KYC"):
            parse_offline_ekyc(b"<SomethingElse><Data/></SomethingElse>")


# ---------------------------------------------------------------------------
# Signature — the part that must not be fooled
# ---------------------------------------------------------------------------

class TestSignature:
    def test_valid_signature_verifies(self, signed):
        valid, reason = verify_xml_signature(signed["xml"], signed["cert"])
        assert valid, reason

    def test_tampered_name_is_caught(self, signed):
        """Change one byte of the payload; the digest must stop matching."""
        forged = signed["xml"].replace(b"Sunita Devi", b"Someone Else")
        valid, reason = verify_xml_signature(forged, signed["cert"])
        assert not valid
        assert "altered" in reason or "digest" in reason

    def test_tampered_address_is_caught(self, signed):
        forged = signed["xml"].replace(b"Ballia", b"Lucknow")
        valid, _ = verify_xml_signature(forged, signed["cert"])
        assert not valid

    def test_a_different_signer_is_rejected(self, signed):
        """A document signed by anyone other than UIDAI must not verify."""
        other_cert = _self_signed_cert(_keypair())
        valid, _ = verify_xml_signature(signed["xml"], other_cert)
        assert not valid

    def test_unsigned_document_is_rejected(self):
        from lxml import etree
        root = etree.Element("OfflinePaperlessKyc", referenceId="8123")
        etree.SubElement(etree.SubElement(root, "UidData"), "Poi", name="X", dob="", gender="M")
        valid, reason = verify_xml_signature(etree.tostring(root), b"")
        assert not valid
        assert "no UIDAI signature" in reason


# ---------------------------------------------------------------------------
# The graded outcome
# ---------------------------------------------------------------------------

class TestGradedResult:
    def test_valid_file_grades_verified(self, signed):
        result = verify_offline_ekyc(_zip_with(signed["xml"]), "1234", cert_pem=signed["cert"])
        assert result.grade is ProofGrade.VERIFIED
        assert result.ok
        assert result.kyc.name == "Sunita Devi"
        assert "UIDAI signature verified" in result.checks

    def test_tampered_file_grades_declared_not_verified(self, signed):
        forged = signed["xml"].replace(b"Sunita Devi", b"Someone Else")
        result = verify_offline_ekyc(_zip_with(forged), "1234", cert_pem=signed["cert"])
        assert result.grade is ProofGrade.DECLARED
        assert not result.ok

    def test_without_a_configured_certificate_it_says_so(self, signed, monkeypatch):
        """Never claim verification we didn't perform."""
        from pathlib import Path
        import src.verification as verification
        monkeypatch.setattr(verification, "UIDAI_CERT_PATH", Path("/nonexistent/cert.pem"))
        result = verify_offline_ekyc(_zip_with(signed["xml"]), "1234")
        assert result.grade is ProofGrade.DECLARED
        assert "certificate isn't configured" in result.reason
        assert result.kyc.name == "Sunita Devi"   # details still read

    def test_description_never_leaks_the_full_aadhaar(self, signed):
        result = verify_offline_ekyc(_zip_with(signed["xml"]), "1234", cert_pem=signed["cert"])
        text = describe(result)
        assert "8123" in text
        assert "never shared" in text

    def test_failed_verification_still_promises_a_recommendation(self, signed):
        forged = signed["xml"].replace(b"Ballia", b"Lucknow")
        result = verify_offline_ekyc(_zip_with(forged), "1234", cert_pem=signed["cert"])
        assert "still get your full recommendation" in describe(result)
