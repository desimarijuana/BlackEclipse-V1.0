"""Generated capabilities: detect a gap, build a tested capability, activate it.

A capability is not "code the model wrote". It is a validated manifest plus a
source digest, a contract test, a sandbox result and an activation decision.
Pure read recipes may auto-activate in the workspace after their tests pass;
every effectful or global surface stays approval-gated.
"""

from __future__ import annotations

from .external import CredentialRequirement, ExternalProposal, propose_external
from .handoff import EffectfulHandoff, plan_handoff
from .manifest import CapabilityManifest, CapabilityPort
from .request import CapabilityAssessment, CapabilityRequest, assess

__all__ = [
    "CapabilityAssessment",
    "CapabilityManifest",
    "CapabilityPort",
    "CapabilityRequest",
    "CredentialRequirement",
    "EffectfulHandoff",
    "ExternalProposal",
    "assess",
    "plan_handoff",
    "propose_external",
]
