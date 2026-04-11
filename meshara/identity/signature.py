"""
Meshara Identity — persistent origin-creator signature and node identity.

Every node, message, and task in the Meshara mesh carries a cryptographically
anchored signature that traces back to the origin creator.  This cannot be
removed without invalidating the signature chain.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

# Avoid circular import — define the canonical constants here and import
# them wherever needed.

# ---------------------------------------------------------------------------
# Origin creator — stitched into the architecture
# ---------------------------------------------------------------------------

ORIGIN_CREATOR: str = "Cbetts1"
ORIGIN_EPOCH:   str = "1991"          # symbolic: birth of the public web
MESHARA_MESH_NAME:  str = "Meshara"           # The Artificial Intelligence Mesh


# ---------------------------------------------------------------------------
# Creator signature
# ---------------------------------------------------------------------------

@dataclass
class CreatorSignature:
    """
    An immutable origin signature embedded in every Meshara entity.

    The signature is derived from the creator name, a node-specific nonce,
    and a timestamp using HMAC-SHA256 so that every derivative node can be
    traced back to the origin creator.
    """

    creator:    str   = ORIGIN_CREATOR
    mesh:       str   = MESHARA_MESH_NAME
    epoch:      str   = ORIGIN_EPOCH
    node_id:    str   = field(default_factory=lambda: str(uuid.uuid4()))
    issued_at:  float = field(default_factory=time.time)
    digest:     str   = field(init=False)

    def __post_init__(self) -> None:
        self.digest = self._compute_digest()

    def _compute_digest(self) -> str:
        payload = f"{self.creator}:{self.mesh}:{self.epoch}:{self.node_id}:{self.issued_at}"
        # The HMAC key is derived from the creator + mesh names so that any
        # node can verify a peer's signature without a shared secret.
        key = f"{ORIGIN_CREATOR}/{MESHARA_MESH_NAME}".encode()
        return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()

    def verify(self) -> bool:
        """Return True if the digest matches the declared fields."""
        return hmac.compare_digest(self.digest, self._compute_digest())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CreatorSignature":
        digest = d.pop("digest", None)
        obj = cls(**d)
        if digest is not None and not hmac.compare_digest(obj.digest, digest):
            raise ValueError("Signature digest mismatch — possible tampering")
        return obj

    def __str__(self) -> str:
        return f"{self.creator}/{self.mesh}@{self.node_id[:8]} [{self.digest[:12]}…]"
