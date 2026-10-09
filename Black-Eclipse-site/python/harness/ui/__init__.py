"""UI Engineering runtime — the AI-native UI catalog, blueprint engine and tools.

Public surface: the models (`model`), the component catalog (`catalog`), the
validation + mutation engine (`engine`), the durable store (`store`), the
service authority (`service`), the agent tools (`tools`) and boot wiring
(`bootstrap`).
"""

from .bootstrap import get_ui_service, install_ui_layer, set_ui_service
from .catalog import CatalogError, UiCatalog, builtin_specs, validate_component_config
from .engine import apply_ops, diff_blueprints, validate_blueprint, widget_count
from .engineering import UiEngineering, UiEngineeringError
from .mode import ModeDecision, UiMode, classify_request
from .model import (
    Availability,
    BlueprintKind,
    BlueprintScope,
    CatalogQuery,
    CreatePageInput,
    UiBlueprint,
    UiComponentSpec,
    UiOperation,
)
from .service import UiError, UiService
from .store import UiStore
from .tools import MUTATION_TOOLS, READ_TOOLS, UI_TOOLS, register_ui_tools

__all__ = [
    "Availability",
    "BlueprintKind",
    "BlueprintScope",
    "CatalogError",
    "CatalogQuery",
    "CreatePageInput",
    "MUTATION_TOOLS",
    "ModeDecision",
    "READ_TOOLS",
    "UI_TOOLS",
    "UiBlueprint",
    "UiCatalog",
    "UiComponentSpec",
    "UiEngineering",
    "UiEngineeringError",
    "UiError",
    "UiMode",
    "UiOperation",
    "UiService",
    "UiStore",
    "apply_ops",
    "builtin_specs",
    "classify_request",
    "diff_blueprints",
    "get_ui_service",
    "install_ui_layer",
    "register_ui_tools",
    "set_ui_service",
    "validate_blueprint",
    "validate_component_config",
    "widget_count",
]
