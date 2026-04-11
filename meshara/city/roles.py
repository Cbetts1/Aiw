"""
Meshara City — role definitions, city-specific intents, and ledger event kinds.

Every bot and citizen in the city carries an explicit role so that the
Governor can route tasks correctly and Protection Agents can audit
membership quickly.
"""

from __future__ import annotations

from enum import Enum


class CityRole(str, Enum):
    """The recognised roles within an Meshara city."""
    GOVERNOR  = "governor"
    PROTECTOR = "protector"
    BUILDER   = "builder"
    EDUCATOR  = "educator"
    ARCHITECT = "architect"
    CITIZEN   = "citizen"


class CityIntent(str, Enum):
    """City-level intents that extend the core Meshara Intent taxonomy."""
    PROTECT       = "protect"
    BUILD         = "build"
    EDUCATE       = "educate"
    DESIGN        = "design"
    CITIZEN_JOIN  = "citizen_join"
    CITIZEN_LEAVE = "citizen_leave"
    CITY_STATUS   = "city_status"
    ALERT         = "alert"
    AUDIT         = "audit"
    POLICY        = "policy"


class CityEventKind(str, Enum):
    """Ledger event kinds used by city bots."""
    CITIZEN_JOINED     = "citizen_joined"
    CITIZEN_LEFT       = "citizen_left"
    BOT_DEPLOYED       = "bot_deployed"
    THREAT_DETECTED    = "threat_detected"
    BUILD_COMPLETED    = "build_completed"
    AUDIT_PASSED       = "audit_passed"
    AUDIT_FAILED       = "audit_failed"
    POLICY_ISSUED      = "policy_issued"
    ALERT_RAISED       = "alert_raised"
    INTEGRITY_VERIFIED = "integrity_verified"
    INTEGRITY_VIOLATED = "integrity_violated"
