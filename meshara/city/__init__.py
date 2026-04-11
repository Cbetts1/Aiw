"""
Meshara City — governed mesh of specialised AI bots.

Five built-in bot roles form the backbone of every Meshara city:

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

from meshara.city.roles import CityRole, CityIntent, CityEventKind
from meshara.city.governor import CityGovernorBot
from meshara.city.citizen import CitizenNode
from meshara.city.protector import ProtectionAgent
from meshara.city.builder import BuilderBot
from meshara.city.educator import EducationBot
from meshara.city.architect import ArchitectBot
from meshara.city.integrity import IntegrityGuard
from meshara.city.launcher import CityLauncher, CityConfig

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
