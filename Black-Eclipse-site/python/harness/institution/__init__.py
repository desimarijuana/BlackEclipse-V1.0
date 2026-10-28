"""The Institution multi-agent preset (analyst -> debate -> trader -> risk -> PM).

A composition layer over the existing team/A2A/task runtime. It adds no agent
loop, no store and no model adapter.
"""

from .bootstrap import install_institution_layer
from .cast import PRESET_ID, PRESET_NAME, PRESET_VERSION, ROLES
from .preset import InstitutionPreset, bot_specs, build_team, descriptor

__all__ = [
    "InstitutionPreset",
    "PRESET_ID",
    "PRESET_NAME",
    "PRESET_VERSION",
    "ROLES",
    "bot_specs",
    "build_team",
    "descriptor",
    "install_institution_layer",
]
