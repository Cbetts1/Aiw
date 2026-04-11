"""Tests for the Meshara optional Ed25519 PKI layer (meshara/identity/pki.py)."""

import pytest

from meshara.identity.pki import NodeKeyPair, is_pki_available


# ---------------------------------------------------------------------------
# Availability guard
# ---------------------------------------------------------------------------

pki_only = pytest.mark.skipif(
    not is_pki_available(),
    reason="cryptography package not installed — PKI tests skipped",
)


class TestPKIAvailability:
    def test_is_pki_available_returns_bool(self):
        result = is_pki_available()
        assert isinstance(result, bool)

    def test_import_error_when_unavailable(self):
        """When cryptography is absent, calling generate() raises ImportError."""
        if is_pki_available():
            pytest.skip("cryptography is installed; skip absence test")
        with pytest.raises(ImportError, match="cryptography"):
            NodeKeyPair.generate()


@pki_only
class TestNodeKeyPairGenerate:
    def test_generate_returns_node_key_pair(self):
        kp = NodeKeyPair.generate()
        assert isinstance(kp, NodeKeyPair)

    def test_public_key_b64_is_string(self):
        kp = NodeKeyPair.generate()
        assert isinstance(kp.public_key_b64, str)
        # Ed25519 public key is 32 bytes → 44 base64 chars (with padding)
        assert len(kp.public_key_b64) == 44

    def test_unique_key_pairs(self):
        keys = {NodeKeyPair.generate().public_key_b64 for _ in range(10)}
        assert len(keys) == 10

    def test_private_key_bytes_is_bytes(self):
        kp = NodeKeyPair.generate()
        assert isinstance(kp.private_key_bytes, bytes)
        assert len(kp.private_key_bytes) == 32

    def test_round_trip_from_private_bytes(self):
        kp = NodeKeyPair.generate()
        raw = kp.private_key_bytes
        kp2 = NodeKeyPair.from_private_bytes(raw)
        assert kp.public_key_b64 == kp2.public_key_b64


@pki_only
class TestSigning:
    def test_sign_returns_bytes(self):
        kp = NodeKeyPair.generate()
        sig = kp.sign(b"hello meshara")
        assert isinstance(sig, bytes)
        assert len(sig) == 64  # Ed25519 signatures are always 64 bytes

    def test_verify_valid_signature(self):
        kp = NodeKeyPair.generate()
        data = b"test message"
        sig = kp.sign(data)
        assert kp.verify(data, sig) is True

    def test_verify_invalid_signature(self):
        kp = NodeKeyPair.generate()
        data = b"test message"
        sig = kp.sign(data)
        tampered = sig[:32] + bytes([sig[32] ^ 0xFF]) + sig[33:]
        assert kp.verify(data, tampered) is False

    def test_verify_wrong_data(self):
        kp = NodeKeyPair.generate()
        sig = kp.sign(b"original")
        assert kp.verify(b"different", sig) is False

    def test_verify_with_public_key_static(self):
        kp = NodeKeyPair.generate()
        data = b"static verify test"
        sig = kp.sign(data)
        assert NodeKeyPair.verify_with_public_key(kp.public_key_b64, data, sig) is True

    def test_verify_with_wrong_public_key(self):
        kp1 = NodeKeyPair.generate()
        kp2 = NodeKeyPair.generate()
        data = b"cross key test"
        sig = kp1.sign(data)
        # Verifying kp1's signature with kp2's public key must fail
        assert NodeKeyPair.verify_with_public_key(kp2.public_key_b64, data, sig) is False

    def test_verify_with_invalid_b64_returns_false(self):
        result = NodeKeyPair.verify_with_public_key("not-valid-b64!!!", b"data", b"\x00" * 64)
        assert result is False


@pki_only
class TestMessageSigning:
    def test_sign_message_returns_string(self):
        kp = NodeKeyPair.generate()
        sig_b64 = kp.sign_message("msg-uuid-1234", 1234567890.0)
        assert isinstance(sig_b64, str)

    def test_verify_message_valid(self):
        kp = NodeKeyPair.generate()
        msg_id = "test-message-id"
        ts = 1700000000.0
        sig_b64 = kp.sign_message(msg_id, ts)
        assert NodeKeyPair.verify_message(kp.public_key_b64, msg_id, ts, sig_b64) is True

    def test_verify_message_wrong_id(self):
        kp = NodeKeyPair.generate()
        sig_b64 = kp.sign_message("real-id", 1700000000.0)
        assert NodeKeyPair.verify_message(kp.public_key_b64, "fake-id", 1700000000.0, sig_b64) is False

    def test_verify_message_wrong_timestamp(self):
        kp = NodeKeyPair.generate()
        sig_b64 = kp.sign_message("msg-id", 1700000000.0)
        assert NodeKeyPair.verify_message(kp.public_key_b64, "msg-id", 9999999999.0, sig_b64) is False

    def test_verify_message_wrong_key(self):
        kp1 = NodeKeyPair.generate()
        kp2 = NodeKeyPair.generate()
        sig_b64 = kp1.sign_message("msg-id", 1700000000.0)
        assert NodeKeyPair.verify_message(kp2.public_key_b64, "msg-id", 1700000000.0, sig_b64) is False
