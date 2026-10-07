"""The browser configuration section.

Eclipse has no YAML config file; configuration is env-var driven with a
dataclass default, exactly like the workflow flag (`HARNESS_WORKFLOWS_ENABLED`).
An optional JSON override at `<app>/.black-eclipse/browser.json` lets an operator
express the nested `browser:` object from the design without hand-writing env
vars; env always wins over the file, and the file always wins over the defaults.

This module only READS configuration. It never launches a browser.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Where browser artifacts live, relative to the app root. Gitignored (the same
# tier as agent-memory.db), never the JDdS vault, never the operator's checkout.
_ARTIFACTS_RELPATH = ".black-eclipse/browser"

# Hard, non-negotiable ceilings. An operator may lower a limit but not remove it.
MAX_SESSIONS_CEILING = 16
MAX_STEPS_CEILING = 500
MAX_EXEC_SECONDS_CEILING = 3_600


def _truthy(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(value: Optional[str], default: int, *, low: int, high: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(parsed, high))


def _app_root() -> Optional[Path]:
    try:
        from ..eclipse_memory.config import repo_root  # noqa: PLC0415

        resolved = repo_root()
        return Path(resolved) if resolved else None
    except Exception:  # noqa: BLE001 - a missing config is simply no app root
        return None


@dataclass
class BrowserConfig:
    """The resolved `browser:` configuration for this process."""

    enabled: bool = True
    default_provider: str = "auto"
    # Local Chromium (the default, Eclipse-managed instance).
    local_enabled: bool = True
    browser_type: str = "chromium"
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None
    proxy: Optional[str] = None
    # CDP: connect to an existing Chrome/Chromium.
    cdp_enabled: bool = True
    cdp_endpoint: Optional[str] = None
    # Optional cloud/alternate backends (all default OFF — discovery is not
    # activation, and a missing runtime dependency is an honest UNAVAILABLE).
    browser_use_enabled: bool = False
    browserbase_enabled: bool = False
    browserbase_project_id: Optional[str] = None
    browserbase_api_key_ref: Optional[str] = None  # a vault reference, never a key
    firecrawl_enabled: bool = False
    firecrawl_endpoint: Optional[str] = None  # a self-hosted Firecrawl base URL
    lightpanda_enabled: bool = False
    lightpanda_endpoint: Optional[str] = None
    agent_browser_enabled: bool = False
    camofox_enabled: bool = False
    camofox_endpoint: Optional[str] = None  # Camoufox CDP/launch endpoint
    # Router maturity (Phase 9.5): prefer the cheapest fitting backend, and allow
    # a private target to reach a remote provider when explicitly authorized.
    prefer_low_cost: bool = False
    allow_private_remote: bool = False
    # Security policy.
    sandbox: bool = True
    allow_credentials: bool = False
    allow_payments: bool = False
    # Sessions.
    max_concurrent: int = 4
    idle_timeout_seconds: int = 900
    # Limits.
    max_steps: int = 100
    max_execution_seconds: int = 900
    # Snapshot context budget (tokens × CHARS_PER_TOKEN); over it the full text is
    # persisted and the model gets a paginated head + the path.
    snapshot_max_chars: int = 24_000
    # Cost rates (Phase 8). ALL default 0 = no price is invented; a measurement is
    # always recorded, a money figure appears only when a rate is configured.
    cost_local_second_micros: int = 0
    cost_cloud_second_micros: int = 0
    cost_vision_token_micros: int = 0
    cost_screenshot_micros: int = 0
    cost_artifact_mb_micros: int = 0
    # Observability.
    telemetry_log_cap: int = 500
    # Artifact directories (all confined under `artifacts_root`).
    artifacts_root: Path = field(default_factory=Path)
    profiles_dir: Path = field(default_factory=Path)
    downloads_dir: Path = field(default_factory=Path)
    uploads_dir: Path = field(default_factory=Path)
    snapshots_dir: Path = field(default_factory=Path)
    screenshots_dir: Path = field(default_factory=Path)
    traces_dir: Path = field(default_factory=Path)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "default_provider": self.default_provider,
            "local": {"enabled": self.local_enabled, "browser": self.browser_type, "headless": self.headless},
            "cdp": {"enabled": self.cdp_enabled},
            "browser_use": {"enabled": self.browser_use_enabled},
            "browserbase": {"enabled": self.browserbase_enabled, "configured": bool(self.browserbase_api_key_ref)},
            "firecrawl": {"enabled": self.firecrawl_enabled},
            "lightpanda": {"enabled": self.lightpanda_enabled},
            "agent_browser": {"enabled": self.agent_browser_enabled},
            "camofox": {"enabled": self.camofox_enabled},
            "router": {"prefer_low_cost": self.prefer_low_cost, "allow_private_remote": self.allow_private_remote},
            "security": {
                "sandbox": self.sandbox,
                "allow_credentials": self.allow_credentials,
                "allow_payments": self.allow_payments,
            },
            "sessions": {"max_concurrent": self.max_concurrent, "idle_timeout_seconds": self.idle_timeout_seconds},
            "limits": {"max_steps": self.max_steps, "max_execution_seconds": self.max_execution_seconds},
            "snapshotMaxChars": self.snapshot_max_chars,
            "cost": {
                "localSecondMicros": self.cost_local_second_micros,
                "cloudSecondMicros": self.cost_cloud_second_micros,
                "visionTokenMicros": self.cost_vision_token_micros,
                "screenshotMicros": self.cost_screenshot_micros,
                "artifactMbMicros": self.cost_artifact_mb_micros,
            },
            "artifactsRoot": str(self.artifacts_root),
        }


def _config_file_overrides() -> dict[str, Any]:
    """A best-effort read of `<app>/.black-eclipse/browser.json` (or the env name).

    Never raises: a malformed or absent file simply contributes nothing.
    """
    root = _app_root()
    if root is None:
        return {}
    override_path = os.environ.get("HARNESS_BROWSER_CONFIG")
    path = Path(override_path) if override_path else root / ".black-eclipse" / "browser.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    # Accept either a top-level `browser:` wrapper or the object directly.
    browser = payload.get("browser")
    return browser if isinstance(browser, dict) else payload


def _dir(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    if raw:
        return Path(raw).expanduser()
    return default


def load_browser_config() -> BrowserConfig:
    """Resolve the browser configuration from defaults, the JSON override, env."""
    file_overrides = _config_file_overrides()

    def top(key: str, default: Any) -> Any:
        """A flat key from the file object, else the default."""
        return file_overrides.get(key, default)

    def nested(section: str, key: str, default: Any) -> Any:
        """A key inside a `section` block, else a flat key, else the default."""
        block = file_overrides.get(section)
        if isinstance(block, dict) and key in block:
            return block[key]
        return file_overrides.get(key, default)

    app_root = _app_root()
    default_artifacts = (app_root / _ARTIFACTS_RELPATH) if app_root else Path(".black-eclipse/browser")
    artifacts_root = _dir("HARNESS_BROWSER_ARTIFACTS_DIR", default_artifacts)

    local = nested("local", "enabled", True)
    security = file_overrides.get("security") if isinstance(file_overrides.get("security"), dict) else {}
    sessions = file_overrides.get("sessions") if isinstance(file_overrides.get("sessions"), dict) else {}
    limits = file_overrides.get("limits") if isinstance(file_overrides.get("limits"), dict) else {}

    cfg = BrowserConfig(
        enabled=_truthy(os.environ.get("HARNESS_BROWSER_ENABLED"), bool(top("enabled", True))),
        default_provider=os.environ.get("HARNESS_BROWSER_PROVIDER") or str(top("default_provider", "auto")),
        local_enabled=_truthy(os.environ.get("HARNESS_BROWSER_LOCAL_ENABLED"), bool(local)),
        browser_type=str(nested("local", "browser", "chromium")),
        headless=_truthy(os.environ.get("HARNESS_BROWSER_HEADLESS"), bool(nested("local", "headless", True))),
        viewport_width=_int(os.environ.get("HARNESS_BROWSER_VIEWPORT_WIDTH"), int(nested("local", "viewportWidth", 1280)), low=200, high=4_000),
        viewport_height=_int(os.environ.get("HARNESS_BROWSER_VIEWPORT_HEIGHT"), int(nested("local", "viewportHeight", 800)), low=200, high=4_000),
        user_agent=os.environ.get("HARNESS_BROWSER_USER_AGENT") or nested("local", "userAgent", None),
        locale=os.environ.get("HARNESS_BROWSER_LOCALE") or nested("local", "locale", None),
        timezone=os.environ.get("HARNESS_BROWSER_TIMEZONE") or nested("local", "timezone", None),
        proxy=os.environ.get("HARNESS_BROWSER_PROXY") or nested("local", "proxy", None),
        cdp_enabled=_truthy(os.environ.get("HARNESS_BROWSER_CDP_ENABLED"), bool(nested("cdp", "enabled", True))),
        cdp_endpoint=os.environ.get("HARNESS_BROWSER_CDP_ENDPOINT") or nested("cdp", "endpoint", None),
        browser_use_enabled=_truthy(os.environ.get("HARNESS_BROWSER_USE_ENABLED"), bool(nested("browser_use", "enabled", False))),
        browserbase_enabled=_truthy(os.environ.get("HARNESS_BROWSERBASE_ENABLED"), bool(nested("browserbase", "enabled", False))),
        browserbase_project_id=os.environ.get("HARNESS_BROWSERBASE_PROJECT_ID") or nested("browserbase", "projectId", None),
        browserbase_api_key_ref=os.environ.get("HARNESS_BROWSERBASE_API_KEY_REF") or nested("browserbase", "apiKeyRef", None),
        firecrawl_enabled=_truthy(os.environ.get("HARNESS_FIRECRAWL_ENABLED"), bool(nested("firecrawl", "enabled", False))),
        firecrawl_endpoint=os.environ.get("HARNESS_FIRECRAWL_ENDPOINT") or nested("firecrawl", "endpoint", None),
        lightpanda_enabled=_truthy(os.environ.get("HARNESS_LIGHTPANDA_ENABLED"), bool(nested("lightpanda", "enabled", False))),
        lightpanda_endpoint=os.environ.get("HARNESS_LIGHTPANDA_ENDPOINT") or nested("lightpanda", "endpoint", None),
        agent_browser_enabled=_truthy(os.environ.get("HARNESS_AGENT_BROWSER_ENABLED"), bool(nested("agent_browser", "enabled", False))),
        camofox_enabled=_truthy(os.environ.get("HARNESS_CAMOFOX_ENABLED"), bool(nested("camofox", "enabled", False))),
        camofox_endpoint=os.environ.get("HARNESS_CAMOFOX_ENDPOINT") or nested("camofox", "endpoint", None),
        prefer_low_cost=_truthy(os.environ.get("HARNESS_BROWSER_PREFER_LOW_COST"), bool(nested("router", "prefer_low_cost", False))),
        allow_private_remote=_truthy(os.environ.get("HARNESS_BROWSER_ALLOW_PRIVATE_REMOTE"), bool(nested("router", "allow_private_remote", False))),
        sandbox=_truthy(os.environ.get("HARNESS_BROWSER_SANDBOX"), bool(security.get("sandbox", True))),
        allow_credentials=_truthy(os.environ.get("HARNESS_BROWSER_ALLOW_CREDENTIALS"), bool(security.get("allow_credentials", False))),
        allow_payments=_truthy(os.environ.get("HARNESS_BROWSER_ALLOW_PAYMENTS"), bool(security.get("allow_payments", False))),
        max_concurrent=_int(os.environ.get("HARNESS_BROWSER_MAX_SESSIONS"), int(sessions.get("max_concurrent", 4)), low=1, high=MAX_SESSIONS_CEILING),
        idle_timeout_seconds=_int(os.environ.get("HARNESS_BROWSER_IDLE_TIMEOUT"), int(sessions.get("idle_timeout_seconds", 900)), low=30, high=86_400),
        max_steps=_int(os.environ.get("HARNESS_BROWSER_MAX_STEPS"), int(limits.get("max_steps", 100)), low=1, high=MAX_STEPS_CEILING),
        max_execution_seconds=_int(os.environ.get("HARNESS_BROWSER_MAX_EXEC_SECONDS"), int(limits.get("max_execution_seconds", 900)), low=5, high=MAX_EXEC_SECONDS_CEILING),
        snapshot_max_chars=_int(os.environ.get("HARNESS_BROWSER_SNAPSHOT_CHARS"), int(top("snapshotMaxChars", 24_000)), low=1_000, high=200_000),
        cost_local_second_micros=_int(os.environ.get("HARNESS_BROWSER_COST_LOCAL_SECOND_MICROS"), int((file_overrides.get("cost") or {}).get("localSecondMicros", 0)), low=0, high=100_000_000),
        cost_cloud_second_micros=_int(os.environ.get("HARNESS_BROWSER_COST_CLOUD_SECOND_MICROS"), int((file_overrides.get("cost") or {}).get("cloudSecondMicros", 0)), low=0, high=100_000_000),
        cost_vision_token_micros=_int(os.environ.get("HARNESS_BROWSER_COST_VISION_TOKEN_MICROS"), int((file_overrides.get("cost") or {}).get("visionTokenMicros", 0)), low=0, high=100_000_000),
        cost_screenshot_micros=_int(os.environ.get("HARNESS_BROWSER_COST_SCREENSHOT_MICROS"), int((file_overrides.get("cost") or {}).get("screenshotMicros", 0)), low=0, high=100_000_000),
        cost_artifact_mb_micros=_int(os.environ.get("HARNESS_BROWSER_COST_ARTIFACT_MB_MICROS"), int((file_overrides.get("cost") or {}).get("artifactMbMicros", 0)), low=0, high=100_000_000),
        telemetry_log_cap=_int(os.environ.get("HARNESS_BROWSER_TELEMETRY_LOG_CAP"), int(top("telemetryLogCap", 500)), low=50, high=10_000),
        artifacts_root=artifacts_root,
    )
    cfg.profiles_dir = _dir("HARNESS_BROWSER_PROFILES_DIR", artifacts_root / "profiles")
    cfg.downloads_dir = _dir("HARNESS_BROWSER_DOWNLOADS_DIR", artifacts_root / "downloads")
    cfg.uploads_dir = _dir("HARNESS_BROWSER_UPLOADS_DIR", artifacts_root / "uploads")
    cfg.snapshots_dir = artifacts_root / "snapshots"
    cfg.screenshots_dir = artifacts_root / "screenshots"
    cfg.traces_dir = artifacts_root / "traces"
    return cfg


# ── Public helpers (the ONE place the config is resolved) ────────────────────

_CONFIG_CACHE: Optional[BrowserConfig] = None


def browser_config(refresh: bool = False) -> BrowserConfig:
    """The process-wide browser configuration (resolved once, env-driven).

    Cached so a tool call does not re-read the file system; `refresh=True`
    re-resolves (used by the routes after an operator change, and by tests).
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None or refresh:
        _CONFIG_CACHE = load_browser_config()
    return _CONFIG_CACHE


def browser_enabled() -> bool:
    """Whether the browser toolset is enabled for this process."""
    return browser_config().enabled


__all__ = [
    "BrowserConfig",
    "MAX_EXEC_SECONDS_CEILING",
    "MAX_SESSIONS_CEILING",
    "MAX_STEPS_CEILING",
    "browser_config",
    "browser_enabled",
    "load_browser_config",
]
