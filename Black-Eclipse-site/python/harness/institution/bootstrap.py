"""Boot wiring for the Institution preset.

Installed AFTER the A2A and team layers, because it registers role presets on the
same seam those layers use. Best-effort, like every other layer: a preset that
cannot install never blocks boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.institution.bootstrap")


def install_institution_layer(service: Any) -> bool:
    """Register the committee's tools, role presets and A2A definitions."""
    if getattr(service, "institution", None) is not None:
        return True
    try:
        registry = getattr(service, "registry", None)
        if registry is not None:
            from .tools import register_institution_tools  # noqa: PLC0415

            register_institution_tools(registry)

        a2a = getattr(service, "a2a", None)
        if a2a is None:
            from ..a2a.bootstrap import install_a2a_layer  # noqa: PLC0415

            install_a2a_layer(service)
            a2a = getattr(service, "a2a", None)

        from .preset import (  # noqa: PLC0415
            InstitutionPreset,
            a2a_definitions,
            agent_configs,
        )

        if a2a is not None:
            a2a._install_agent_configs(agent_configs())  # noqa: SLF001 - the shared seam
            try:
                from ..a2a.model import AgentDefinition  # noqa: PLC0415

                for raw in a2a_definitions():
                    try:
                        a2a.registry.register_agent(AgentDefinition(**raw))
                    except Exception:  # noqa: BLE001 - an existing id is fine
                        continue
            except Exception:  # noqa: BLE001 - presets still run without the registry
                log.warning("institution A2A definitions unavailable", exc_info=True)

        service.institution = InstitutionPreset()
        return True
    except Exception:  # noqa: BLE001 - the preset must never block boot
        log.warning("institution preset unavailable", exc_info=True)
        service.institution = None
        return False


__all__ = ["install_institution_layer"]
