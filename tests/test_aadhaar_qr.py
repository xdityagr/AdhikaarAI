"""
Reading the Secure QR printed on an Aadhaar card.

There is no real Aadhaar QR in this repository and there never will be, so the
fixtures are built to UIDAI's published layout and signed with a throwaway key
generated in the test. That exercises every step for real — big integer, gzip,
0xFF-delimited fields, photograph, trailing RSA signature — while the only card
this suite can prove is one it made up.

The camera, a worn card and a dim room are the parts a synthetic payload cannot
speak to. Those need a real card and a real phone.
"""

import gzip
import os

import pytest

from src import aadhaar_qr


# ---------------------------------------------------------------------------
# Building a card to the spec
# ---------------------------------------------------------------------------

FIELDS = [
    "2",                      # a mobile hash follows the photograph
    "1234202603081200000",    # reference id: last4 + timestamp
    "Sunita Devi",
    "12-04-1988",
    "F",
    "W/O Ram Prasad",
    "Ballia",                 # district
    "Near the school",        # landmark
    "House 14",
    "Rampur",                 # location
    "277001",                 # pincode
    "Rampur PO",
    "Uttar Pradesh",
    "Station Road",
    "Bansdih",                # sub-district
    "Rampur",                 # vtc — often the same as location
]

PHOTO = bytes(range(256)) * 4          # stands in for the JPEG2000 portrait
MOBILE_HASH = b"\x11" * 32


def _payload() -> bytes:
    body = b"\xff".join(f.encode("utf-8") for f in FIELDS) + b"\xff"
    return body + PHOTO + MOBILE_HASH


def _key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _certificate(key):
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test UIDAI")])
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
    from cryptography.hazmat.primitives import serialization
    return cert.public_bytes(serialization.Encoding.PEM)


def _sign(key, data: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    return key.sign(data, padding.PKCS1v15(), hashes.SHA256())


def _qr_text(signed: bool = True, key=None) -> str:
    """A whole card, as the string a scanner hands back."""
    body = _payload()
    if signed:
        # The signature covers the DECOMPRESSED bytes that precede it, so it
        # is appended before the whole thing is gzipped.
        raw = body + _sign(key, body)
    else:
        raw = body + b"\x00" * aadhaar_qr.SIGNATURE_BYTES
    packed = gzip.compress(raw)
    return str(int.from_bytes(packed, "big"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDecoding:
    def test_a_card_reads_back_as_demographics(self):
        scanned = aadhaar_qr.scan(_qr_text(signed=False))
        assert scanned.name == "Sunita Devi"
        assert scanned.dob == "12-04-1988"
        assert scanned.gender == "F"
        assert scanned.district == "Ballia"
        assert scanned.state == "Uttar Pradesh"
        assert scanned.pincode == "277001"

    def test_only_the_last_four_digits_exist_anywhere(self):
        """The QR carries no Aadhaar number, so neither may we."""
        scanned = aadhaar_qr.scan(_qr_text(signed=False))
        assert scanned.aadhaar_last4 == "1234"
        for value in vars(scanned).values():
            if isinstance(value, str):
                assert len(value.strip()) != 12 or not value.strip().isdigit()

    def test_the_photograph_is_discarded(self):
        """The most identifying thing in the payload, and we have no use for
        it. The safest place for data you do not need is nowhere."""
        scanned = aadhaar_qr.scan(_qr_text(signed=False))
        assert not hasattr(scanned, "photo")
        assert not hasattr(scanned, "image")

    def test_the_address_is_assembled_in_reading_order(self):
        scanned = aadhaar_qr.scan(_qr_text(signed=False))
        address = scanned.address
        assert address.startswith("House 14")
        assert "Station Road" in address
        assert "Bansdih" in address

    def test_a_repeated_village_is_not_printed_twice(self):
        """UIDAI puts the village in both `location` and `vtc` often enough
        that "Rampur, Rampur" would be the norm rather than the exception.

        Compared segment by segment rather than as a substring: "Rampur PO" is
        the post office and genuinely belongs on the address, even though it
        contains the village name inside it.
        """
        segments = [part.strip().lower() for part in
                    aadhaar_qr.scan(_qr_text(signed=False)).address.split(",")]
        assert len(segments) == len(set(segments))
        assert segments.count("rampur") == 1


class TestSignature:
    def test_a_genuine_signature_verifies(self):
        key = _key()
        scanned = aadhaar_qr.scan(_qr_text(key=key), cert_pem=_certificate(key))
        assert scanned.verified
        assert "UIDAI" in scanned.verify_note

    def test_a_forged_card_does_not_verify(self):
        """Signed by one key, checked against another."""
        scanned = aadhaar_qr.scan(_qr_text(key=_key()),
                                  cert_pem=_certificate(_key()))
        assert not scanned.verified

    def test_tampering_with_the_name_breaks_the_signature(self):
        """The whole point: the signature covers the demographics."""
        key = _key()
        body = _payload().replace(b"Sunita Devi", b"Somebody Else")
        raw = body + _sign(key, _payload())      # signature of the ORIGINAL
        text = str(int.from_bytes(gzip.compress(raw), "big"))
        scanned = aadhaar_qr.scan(text, cert_pem=_certificate(key))
        assert scanned.name == "Somebody Else"
        assert not scanned.verified

    def test_an_unverified_card_is_still_returned(self):
        """A missing certificate is our problem. Refusing to help someone fill
        a form because of it would punish them for our own missing file."""
        scanned = aadhaar_qr.scan(_qr_text(signed=False), cert_pem=None)
        assert scanned.name == "Sunita Devi"
        assert not scanned.verified

    def test_verification_downgrades_the_proof_grade_only(self):
        unverified = aadhaar_qr.to_profile(
            aadhaar_qr.scan(_qr_text(signed=False)))
        assert unverified["proof"] == "declared"
        assert unverified["full_name"] == "Sunita Devi"


class TestRefusals:
    def test_a_plain_string_is_refused(self):
        with pytest.raises(aadhaar_qr.AadhaarQrError):
            aadhaar_qr.scan("https://example.com/not-an-aadhaar")

    def test_nothing_is_refused(self):
        with pytest.raises(aadhaar_qr.AadhaarQrError):
            aadhaar_qr.scan("")

    def test_an_older_short_qr_says_so_rather_than_crashing(self):
        """Letters printed before about 2018 carry a sparse QR. The person
        needs to be told that, not shown a decompression error."""
        with pytest.raises(aadhaar_qr.AadhaarQrError, match="older Aadhaar QR"):
            aadhaar_qr.scan("12345678901234567890")

    def test_a_truncated_card_says_the_qr_ended_early(self):
        """Padded past the older-card length guard, so this exercises the
        field splitter rather than the guard sitting in front of it."""
        # Incompressible padding: 400 identical bytes gzip down to nothing and
        # the payload would still be short enough to trip the guard.
        body = (b"\xff".join(f.encode() for f in FIELDS[:5]) + b"\xff"
                + os.urandom(400))
        text = str(int.from_bytes(gzip.compress(body), "big"))
        with pytest.raises(aadhaar_qr.AadhaarQrError, match="ended early"):
            aadhaar_qr.scan(text)


class TestProfileShape:
    def test_it_fills_the_fields_the_pack_leaves_blank(self):
        profile = aadhaar_qr.to_profile(aadhaar_qr.scan(_qr_text(signed=False)))
        for key in ("full_name", "dob", "gender", "address", "district",
                    "state", "pincode"):
            assert profile.get(key), key

    def test_the_care_of_prefix_is_stripped(self):
        """"W/O Ram Prasad" is a relationship marker, not part of the name."""
        profile = aadhaar_qr.to_profile(aadhaar_qr.scan(_qr_text(signed=False)))
        assert profile["parent_name"] == "Ram Prasad"

    def test_empty_values_are_omitted_not_blanked(self):
        """A field the card did not carry must stay genuinely blank on the
        printed form rather than looking answered."""
        scanned = aadhaar_qr.ScannedAadhaar(name="Only A Name")
        profile = aadhaar_qr.to_profile(scanned)
        assert "pincode" not in profile
        assert "district" not in profile

    def test_the_date_is_converted_for_a_date_input(self):
        assert aadhaar_qr.dob_to_iso("12-04-1988") == "1988-04-12"
        assert aadhaar_qr.dob_to_iso("12/04/1988") == "1988-04-12"

    def test_an_odd_date_is_passed_through_untouched(self):
        assert aadhaar_qr.dob_to_iso("1988") == "1988"

    def test_the_fingerprint_does_not_contain_the_payload(self):
        text = _qr_text(signed=False)
        mark = aadhaar_qr.fingerprint(text)
        assert len(mark) == 12
        assert mark not in text

class TestVersionedCards:
    """Cards issued from about 2022 begin with a version marker.

    One extra field at the front shifts every later field by one, and the
    failure is silent: the form fills with the neighbouring value. A real card
    read its reference id back as the person's name and its gender as their
    father's name, which is how this was found — not by a test.
    """

    def _versioned(self) -> str:
        body = b"\xff".join([b"V2", *[f.encode() for f in FIELDS]]) + b"\xff"
        return str(int.from_bytes(gzip.compress(body + PHOTO + MOBILE_HASH), "big"))

    def test_a_versioned_card_reads_the_same_as_an_unversioned_one(self):
        scanned = aadhaar_qr.scan(self._versioned())
        assert scanned.name == "Sunita Devi"
        assert scanned.gender == "F"
        assert scanned.dob == "12-04-1988"
        assert scanned.state == "Uttar Pradesh"

    def test_the_reference_id_does_not_end_up_in_the_name(self):
        """The exact symptom seen on a real card."""
        scanned = aadhaar_qr.scan(self._versioned())
        assert not scanned.name[:6].isdigit()
        assert scanned.reference_id.isdigit()

    def test_the_gender_does_not_end_up_as_the_parent_name(self):
        profile = aadhaar_qr.to_profile(aadhaar_qr.scan(self._versioned()))
        assert profile.get("parent_name") != "F"
        assert profile.get("parent_name") == "Ram Prasad"

    def test_both_layouts_give_the_same_answer(self):
        plain = aadhaar_qr.scan(_qr_text(signed=False))
        versioned = aadhaar_qr.scan(self._versioned())
        for field in ("name", "dob", "gender", "district", "state", "pincode"):
            assert getattr(plain, field) == getattr(versioned, field), field

    def test_a_layout_we_cannot_place_is_refused(self):
        """Rather than filling a government form with somebody else's fields."""
        scrambled = b"\xff".join(
            [b"junk", b"more junk", *[f.encode() for f in FIELDS[2:]]]) + b"\xff"
        text = str(int.from_bytes(
            gzip.compress(scrambled + PHOTO + MOBILE_HASH), "big"))
        with pytest.raises(aadhaar_qr.AadhaarQrError):
            aadhaar_qr.scan(text)
