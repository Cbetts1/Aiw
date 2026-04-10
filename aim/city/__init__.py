"""
AIM City — governed mesh of specialised AI bots.

Five built-in bot roles form the backbone of every AIM city:

    Governor   — orchestrates all bots and citizens
    Protector  — security, signature verification, threat blacklisting
    Builder    — deploys and registers new nodes
    Educator   — knowledge base and teaching services
    Architect  — topology planning and blueprint management

Plus:
    CitizenNode    — participant nodes that live inside the city
    IntegrityGuard — standalone tamper-detection (runs outside the mesh)
    CityLauncher   — one-call automation to stand up the full fleet
"""

from aim.city.roles import CityRole, CityIntent, CityEventKind
from aim.city.governor import CityGovernorBot
from aim.city.citizen import CitizenNode
from aim.city.protector import ProtectionAgent
from aim.city.builder import BuilderBot
from aim.city.educator import EducationBot
from aim.city.architect import ArchitectBot
from aim.city.integrity import IntegrityGuard
from aim.city.launcher import CityLauncher, CityConfig

__all__ = [
    "CityRole",
    "CityIntent",
    "CityEventKind",
    "CityGovernorBot",
    "CitizenNode",
    "ProtectionAgent",
    "BuilderBot",
    "EducationBot",
    "ArchitectBot",
    "IntegrityGuard",
    "CityLauncher",
    "CityConfig",
]
