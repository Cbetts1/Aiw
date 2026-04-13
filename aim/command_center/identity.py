"""
AIM Command Center — Virtual Device Identity.

Every node that connects to the Command Center carries a VirtualDeviceIdentity
anchored to the origin creator's signature, making the provenance of each
device traceable through the mesh.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from aim.identity.signature import CreatorSignature, ORIGIN_CREATOR, AIM_MESH_NAME


@dataclass
class VirtualDeviceIdentity:
    """
    Unique, cryptographically anchored identity for an AIM virtual device.

    Parameters
    ----------
    device_id    : UUID string auto-generated via :meth:`new`.
    device_name  : Human-readable name for this device.
    repo_url     : Source repository URL.
    capabilities : Advertised capability tags.
    registered_at: Unix timestamp of registration.
    signature    : Origin-creator signature binding this identity to the mesh.
    """

    device_id: str
    device_name: str
    repo_url: str
    capabilities: list[str]
    signature: CreatorSignature
    mesh_name: str = AIM_MESH_NAME
    creator: str = ORIGIN_CREATOR
    registered_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def new(
        cls,
        name: str,
        repo_url: str,
        capabilities: list[str] | None = None,
    ) -> "VirtualDeviceIdentity":
        """Create a new identity with an auto-generated UUID and signature."""
        device_id = str(uuid.uuid4())
        sig = CreatorSignature(node_id=device_id)
        return cls(
            device_id=device_id,
            device_name=name,
            repo_url=repo_url,
            capabilities=capabilities or [],
            signature=sig,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of this identity."""
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "mesh_name": self.mesh_name,
            "creator": self.creator,
            "repo_url": self.repo_url,
            "capabilities": list(self.capabilities),
            "registered_at": self.registered_at,
            "signature": self.signature.to_dict(),
        }

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self) -> bool:
        """Return True if the embedded signature is valid."""
        return self.signature.verify()

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"AIM-NODE:{self.device_id[:8]}@{self.device_name}"
