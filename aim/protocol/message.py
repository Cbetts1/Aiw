"""
AIM Protocol Layer — message format and envelope definitions.

Unlike HTTP (request/response pages), AIM messages carry *intent* and
*context* so that every node can reason about what is being asked rather
than blindly serving a static resource.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from aim.identity.signature import ORIGIN_CREATOR


# ---------------------------------------------------------------------------
# Intent taxonomy
# ---------------------------------------------------------------------------

class Intent(str, Enum):
    """First-class intent types carried by every AIM message."""
    QUERY       = "query"       # ask a question or request information
    TASK        = "task"        # delegate an executable unit of work
    DELEGATE    = "delegate"    # forward a task to another node
    RESPOND     = "respond"     # reply to a prior message
    ANNOUNCE    = "announce"    # broadcast node presence / capability
    HEARTBEAT   = "heartbeat"   # liveness ping
    MEMORY_SET  = "memory_set"  # write to shared cross-node memory
    MEMORY_GET  = "memory_get"  # read from shared cross-node memory
    SPAWN       = "spawn"       # request creation of a child node
    FORWARD     = "forward"     # relay a message through an intermediate hop


class Status(str, Enum):
    """Outcome status carried in RESPOND messages."""
    OK          = "ok"
    ERROR       = "error"
    PENDING     = "pending"
    DELEGATED   = "delegated"


# ---------------------------------------------------------------------------
# Core message envelope
# ---------------------------------------------------------------------------

@dataclass
class AIMMessage:
    """
    An AIM protocol envelope.

    Fields
    ------
    intent      : the semantic purpose of this message
    payload     : arbitrary JSON-serialisable content
    sender_id   : originating node identifier
    receiver_id : target node identifier (None → broadcast)
    message_id  : unique message identifier (auto-generated)
    correlation_id : links a RESPOND back to its originating message
    timestamp   : Unix epoch seconds (auto-generated)
    context     : accumulated conversation / session context
    signature   : origin-creator signature (propagated through all hops)
    ttl         : time-to-live in hops (decremented at each relay node)
    """

    intent:         Intent
    payload:        dict[str, Any]           = field(default_factory=dict)
    sender_id:      str                      = ""
    receiver_id:    str | None               = None
    message_id:     str                      = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None               = None
    timestamp:      float                    = field(default_factory=time.time)
    context:        dict[str, Any]           = field(default_factory=dict)
    signature:      str                      = field(default_factory=lambda: ORIGIN_CREATOR)
    ttl:            int                      = 16

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        d = asdict(self)
        d["intent"] = self.intent.value
        return json.dumps(d)

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @classmethod
    def from_json(cls, raw: str) -> "AIMMessage":
        d = json.loads(raw)
        d["intent"] = Intent(d["intent"])
        return cls(**d)

    @classmethod
    def from_bytes(cls, data: bytes) -> "AIMMessage":
        return cls.from_json(data.decode("utf-8"))

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def query(
        cls,
        text: str,
        sender_id: str = "",
        receiver_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> "AIMMessage":
        return cls(
            intent=Intent.QUERY,
            payload={"text": text},
            sender_id=sender_id,
            receiver_id=receiver_id,
            context=context or {},
        )

    @classmethod
    def task(
        cls,
        name: str,
        args: dict[str, Any] | None = None,
        sender_id: str = "",
        receiver_id: str | None = None,
    ) -> "AIMMessage":
        return cls(
            intent=Intent.TASK,
            payload={"name": name, "args": args or {}},
            sender_id=sender_id,
            receiver_id=receiver_id,
        )

    @classmethod
    def respond(
        cls,
        correlation_id: str,
        result: Any,
        status: Status = Status.OK,
        sender_id: str = "",
        receiver_id: str | None = None,
    ) -> "AIMMessage":
        return cls(
            intent=Intent.RESPOND,
            payload={"result": result, "status": status.value},
            sender_id=sender_id,
            receiver_id=receiver_id,
            correlation_id=correlation_id,
        )

    @classmethod
    def heartbeat(cls, sender_id: str = "") -> "AIMMessage":
        return cls(
            intent=Intent.HEARTBEAT,
            payload={},
            sender_id=sender_id,
        )

    @classmethod
    def announce(cls, capabilities: list[str], sender_id: str = "") -> "AIMMessage":
        return cls(
            intent=Intent.ANNOUNCE,
            payload={"capabilities": capabilities},
            sender_id=sender_id,
        )
