"""
AIM Identity — Optional Ed25519 PKI Layer.

This module provides Ed25519 key-pair generation, message signing, and
signature verification for AIM nodes, enabling open (no shared-secret)
identity verification on the public mesh.

The ``cryptography`` package is **optional**.  Import guards ensure that the
rest of AIM functions normally when ``cryptography`` is not installed.

Usage
-----
    from aim.identity.pki import NodeKeyPair, is_pki_available

    if is_pki_available():
        kp = NodeKeyPair.generate()
        sig = kp.sign(b"hello AIM")
        assert kp.verify(b"hello AIM", sig)

        # Serialize / share the public key
        pub_b64 = kp.public_key_b64
        # Verify from another node using only the public key
        assert NodeKeyPair.verify_with_public_key(pub_b64, b"hello AIM", sig)
"""

from __future__ import annotations

import base64
import importlib.util

# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_pki_available() -> bool:
    """Return ``True`` if the ``cryptography`` package is installed."""
    return importlib.util.find_spec("cryptography") is not None


# ---------------------------------------------------------------------------
# Lazy imports — only resolved when PKI functions are actually called
# ---------------------------------------------------------------------------

def _require_cryptography() -> None:
    if not is_pki_available():
        raise ImportError(
            "The 'cryptography' package is required for AIM PKI features.\n"
            "Install it with:  pip install cryptography"
        )


# ---------------------------------------------------------------------------
# NodeKeyPair
# ---------------------------------------------------------------------------

class NodeKeyPair:
    """
    An Ed25519 key pair bound to an AIM node.

    Parameters
    ----------
    private_key:
        A ``cryptography`` Ed25519PrivateKey object.

    Notes
    -----
    * Never transmit or log the private key.
    * Rotate the key pair periodically for forward secrecy.
    * Store old public keys in the ``LegacyLedger`` for historical verification.
    """

    def __init__(self, private_key: object) -> None:
        _require_cryptography()
        self._private_key = private_key

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def generate(cls) -> "NodeKeyPair":
        """Generate a fresh Ed25519 key pair."""
        _require_cryptography()
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, raw: bytes) -> "NodeKeyPair":
        """Load an Ed25519 private key from 32 raw bytes."""
        _require_cryptography()
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return cls(Ed25519PrivateKey.from_private_bytes(raw))

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        """
        Sign *data* with the node's private key.

        Parameters
        ----------
        data:
            The bytes to sign.

        Returns
        -------
        bytes
            A 64-byte Ed25519 signature.
        """
        _require_cryptography()
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        assert isinstance(self._private_key, Ed25519PrivateKey)
        return self._private_key.sign(data)

    # ------------------------------------------------------------------
    # Verification (instance — owns private key)
    # ------------------------------------------------------------------

    def verify(self, data: bytes, signature: bytes) -> bool:
        """
        Verify *signature* against *data* using this key pair's public key.

        Returns ``True`` on success, ``False`` on failure.
        """
        return NodeKeyPair.verify_with_public_key(
            self.public_key_b64, data, signature
        )

    # ------------------------------------------------------------------
    # Public key export / import
    # ------------------------------------------------------------------

    @property
    def public_key_b64(self) -> str:
        """URL-safe base64-encoded public key (44 characters)."""
        _require_cryptography()
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat
        )
        raw = self._private_key.public_key().public_bytes(  # type: ignore[attr-defined]
            Encoding.Raw, PublicFormat.Raw
        )
        return base64.urlsafe_b64encode(raw).decode("ascii")

    @property
    def private_key_bytes(self) -> bytes:
        """Raw 32-byte private key material.  Handle with extreme care."""
        _require_cryptography()
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption
        )
        return self._private_key.private_bytes(  # type: ignore[attr-defined]
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )

    # ------------------------------------------------------------------
    # Static verification (public-key only)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_with_public_key(
        public_key_b64: str,
        data: bytes,
        signature: bytes,
    ) -> bool:
        """
        Verify *signature* against *data* using a base64-encoded public key.

        This is the method used by receiving nodes that do not hold the private
        key — they only need the sender's advertised ``public_key_b64``.

        Parameters
        ----------
        public_key_b64:
            URL-safe base64-encoded Ed25519 public key.
        data:
            The original signed data.
        signature:
            The 64-byte Ed25519 signature to verify.

        Returns
        -------
        bool
            ``True`` if the signature is valid, ``False`` otherwise.
        """
        _require_cryptography()
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat
        )
        try:
            raw = base64.urlsafe_b64decode(public_key_b64)
            pub = Ed25519PublicKey.from_public_bytes(raw)
            pub.verify(signature, data)
            return True
        except (InvalidSignature, Exception):
            return False

    # ------------------------------------------------------------------
    # AIM message signing helpers
    # ------------------------------------------------------------------

    def sign_message(self, message_id: str, timestamp: float) -> str:
        """
        Sign the canonical representation of an AIM message envelope.

        The signed payload is ``"{message_id}:{timestamp}"`` encoded as UTF-8.

        Returns
        -------
        str
            URL-safe base64-encoded signature suitable for storage in
            ``AIMMessage.context["node_sig"]``.
        """
        payload = f"{message_id}:{timestamp}".encode("utf-8")
        sig_bytes = self.sign(payload)
        return base64.urlsafe_b64encode(sig_bytes).decode("ascii")

    @staticmethod
    def verify_message(
        public_key_b64: str,
        message_id: str,
        timestamp: float,
        sig_b64: str,
    ) -> bool:
        """
        Verify a signed AIM message envelope.

        Parameters
        ----------
        public_key_b64:
            Sender's Ed25519 public key in URL-safe base64.
        message_id:
            The ``message_id`` from the ``AIMMessage``.
        timestamp:
            The ``timestamp`` from the ``AIMMessage``.
        sig_b64:
            The base64-encoded signature from ``AIMMessage.context["node_sig"]``.

        Returns
        -------
        bool
        """
        payload = f"{message_id}:{timestamp}".encode("utf-8")
        sig_bytes = base64.urlsafe_b64decode(sig_b64)
        return NodeKeyPair.verify_with_public_key(public_key_b64, payload, sig_bytes)
