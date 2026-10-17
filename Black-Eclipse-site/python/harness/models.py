"""Universal model provider factory.

Goal: connect EVERY model the operator has a key for, without hard-coding a
vendor into the agent runtime. Two mechanisms cover the field:

  1. Native LangChain integrations for first-party APIs (Anthropic, Google
     Gemini, Mistral, Groq, AWS Bedrock, Cohere, ...).
  2. The OpenAI-compatible protocol for everything else — Ollama, LM Studio,
     vLLM, OpenRouter, DeepSeek, xAI, Perplexity, Together, Fireworks, and any
     custom base URL. This one path alone reaches most hosted + local models.

The catalog is data, not branches: `PROVIDER_CATALOG` declares each provider's
LangChain class, its default base URL, model, and which env var holds its key.
Adding a provider is an entry here plus a requirements line.

Credentials are passed in per run (resolved by the TS vault) — this service
never reads env for secrets except as an explicit fallback.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from .schemas import ModelSettings


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    # LangChain integration family:
    #   "openai"    -> langchain_openai.ChatOpenAI (also all compatible endpoints)
    #   "anthropic" -> langchain_anthropic.ChatAnthropic
    #   "google"    -> langchain_google_genai.ChatGoogleGenerativeAI
    #   "mistral"   -> langchain_mistralai.ChatMistralAI
    #   "groq"      -> langchain_groq.ChatGroq
    kind: str
    default_base_url: Optional[str] = None
    default_model: str = ""
    env_var: Optional[str] = None
    keyless: bool = False
    # OpenAI-compatible endpoints beyond the first-party ones.
    openai_compatible: bool = False
    # True when the provider can enumerate its models on demand (a local server
    # lists its installed models; a hosted API or router lists its live
    # catalog). The UI offers a "Discover" probe for these, and the result is
    # merged into the picker (and cached) so the operator sees the real,
    # current model ids — never only the declared sample. False = the declared
    # list is the whole story.
    dynamic_discovery: bool = False
    # The provider's conservative context window (tokens), or None when it is
    # genuinely unknown. This is the FALLBACK when no model-specific value
    # applies. Where a provider's models vary widely this is a conservative
    # FLOOR, not a best-case maximum — see the provenance comment on each row.
    context_window: Optional[int] = None


# ─── Catalog ─────────────────────────────────────────────────────────────────
# Model IDs are sensible defaults; the operator's saved config wins. "all models
# that exist" is reached through the openai-compatible rows, which accept ANY
# base URL + model id.
#
# `context_window` values are DECLARED, CONSERVATIVE FLOORS from each provider's
# published model documentation, never a best-case maximum. A provider row whose
# hosted models vary widely (a router, or a local server) is left `None` on
# purpose — the runtime then falls back to the conservative history ceiling
# instead of inventing a number (see `resolve_context_window`). Provenance for
# each value is in the trailing comment.
PROVIDER_CATALOG: dict[str, ProviderSpec] = {
    # OpenAI current text models are 128k; the older gpt-3.5-turbo is 16k. The
    # provider row is the floor for an unrecognised OpenAI model.
    "openai": ProviderSpec("openai", "OpenAI", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=128_000),
    # Anthropic Claude 3.x text models are 200k.
    "anthropic": ProviderSpec("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com", "claude-3-5-sonnet-latest", "ANTHROPIC_API_KEY", dynamic_discovery=True, context_window=200_000),
    # Gemini 1.5/2.0 are 1M input tokens.
    "google": ProviderSpec("google", "Google Gemini", "google", None, "gemini-2.0-flash", "GEMINI_API_KEY", dynamic_discovery=True, context_window=1_000_000),
    # Mistral model windows vary (7B is 32k, Large is 128k); the row is the 32k
    # floor, with a model-specific 128k for the large family below.
    "mistral": ProviderSpec("mistral", "Mistral", "mistral", "https://api.mistral.ai/v1", "mistral-large-latest", "MISTRAL_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=32_000),
    # Groq hosts many small 8k models; the row is that floor, with a 128k
    # model-specific value for the Llama-3.3 family below.
    "groq": ProviderSpec("groq", "Groq", "groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=8_192),
    # Local servers: the window is chosen by the operator's loaded model, which
    # the runtime cannot know. Unknown stays unknown (conservative ceiling).
    "ollama": ProviderSpec("ollama", "Ollama (local)", "openai", "http://localhost:11434/v1", "llama3.1", "OLLAMA_BASE_URL", keyless=True, openai_compatible=True, dynamic_discovery=True),
    "lmstudio": ProviderSpec("lmstudio", "LM Studio (local)", "openai", "http://localhost:1234/v1", "local-model", keyless=True, openai_compatible=True, dynamic_discovery=True),
    # DeepSeek V3 chat models are 64k.
    "deepseek": ProviderSpec("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=64_000),
    # Grok 2 is 131k.
    "xai": ProviderSpec("xai", "xAI (Grok)", "openai", "https://api.x.ai/v1", "grok-2-latest", "XAI_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=131_072),
    # A router fronts models with wildly different windows. Do not guess.
    "openrouter": ProviderSpec("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", "OPENROUTER_API_KEY", openai_compatible=True, dynamic_discovery=True),
    # Together/Fireworks host many model families of different sizes. Only the
    # known Llama-3.3 entry is declared (below); the row is left unknown.
    "together": ProviderSpec("together", "Together AI", "openai", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY", openai_compatible=True, dynamic_discovery=True),
    # Perplexity sonar is ~128k.
    "perplexity": ProviderSpec("perplexity", "Perplexity", "openai", "https://api.perplexity.ai", "sonar", "PERPLEXITY_API_KEY", openai_compatible=True, dynamic_discovery=True, context_window=128_000),
    "fireworks": ProviderSpec("fireworks", "Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3p3-70b-instruct", "FIREWORKS_API_KEY", openai_compatible=True, dynamic_discovery=True),
    # Any endpoint not listed: give a base URL and a model id.
    "custom": ProviderSpec("custom", "Custom (OpenAI-compatible)", "openai", None, "", keyless=True, openai_compatible=True, dynamic_discovery=True),
}


# Declared, known model ids per provider, for the settings picker. This is a
# convenience list, never an allowlist — the operator may always type a model id
# the catalog does not know (the OpenAI-compatible path accepts any). Kept here,
# beside the context windows, so the UI never keeps a second, drifting copy.
PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-3.5-turbo"],
    "anthropic": [
        "claude-3-5-sonnet-latest", "claude-3-5-haiku-latest",
        "claude-3-opus-latest", "claude-4-sonnet-latest",
    ],
    "google": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
    "mistral": ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
    "groq": [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
    ],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "xai": ["grok-2-latest", "grok-2-1212", "grok-beta"],
    "perplexity": ["sonar", "sonar-pro", "sonar-reasoning"],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ],
    "fireworks": [
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "accounts/fireworks/models/mixtral-8x7b-instruct",
    ],
    # Local servers and routers list models at runtime; the operator supplies the
    # id. The declared lists include the common open-weight VISION models so the
    # vision subsystem can find a local VLM without a discovery round-trip; the
    # list is a convenience, never an allowlist.
    "ollama": ["llama3.1", "llama3.2", "qwen2.5", "qwen2.5-vl", "llava", "llava-llama3", "minicpm-v", "moondream", "gemma3", "mistral", "phi3"],
    "lmstudio": ["local-model", "llava", "qwen2.5-vl", "gemma-3"],
    "openrouter": [
        "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5",
        "qwen/qwen2.5-vl-72b-instruct", "meta-llama/llama-3.2-11b-vision-instruct",
    ],
}


# Model-specific windows. Keyed by provider id, then by a lowercase model
# SUBSTRING; a longer substring wins over a shorter one (so `gpt-4o-mini-…`
# matches `gpt-4o-mini`, not just `gpt-4o`). Only documented families are listed
# — an unlisted model falls back to the provider row, then to unknown.
MODEL_CONTEXT_WINDOWS: dict[str, dict[str, int]] = {
    "openai": {
        "gpt-4o": 128_000,       # gpt-4o / gpt-4o-mini: 128k input
        "gpt-4.1": 128_000,
        "gpt-3.5-turbo": 16_385,
    },
    "anthropic": {
        "claude-3": 200_000,     # Claude 3.x family: 200k
        "claude-4": 200_000,
    },
    "google": {
        "gemini-2.0": 1_000_000,
        "gemini-1.5": 1_000_000,
    },
    "mistral": {
        "mistral-large": 128_000,
    },
    "groq": {
        "llama-3.3-70b": 128_000,
        "llama-3.1-70b": 128_000,
    },
    "deepseek": {
        "deepseek-chat": 64_000,
        "deepseek-reasoner": 64_000,
    },
    "xai": {
        "grok-2": 131_072,
        "grok-3": 131_072,
    },
    "together": {
        "llama-3.3": 128_000,
    },
    "fireworks": {
        "llama-v3p3": 131_072,
    },
}


def resolve_context_window(provider: str, model: str) -> Optional[int]:
    """The declared context window for a provider+model, or None when unknown.

    Pure and deterministic — no network call. Resolution order:

    1. a model-specific declared window (`MODEL_CONTEXT_WINDOWS`), longest
       matching substring wins;
    2. the provider's declared window (`ProviderSpec.context_window`);
    3. `None` — never a fabricated number.

    A `None` result must be treated as unknown by the caller: the budget falls
    back to the conservative history ceiling and every surface reports "unknown".
    """
    provider_models = MODEL_CONTEXT_WINDOWS.get((provider or "").lower())
    if provider_models and model:
        needle = model.lower()
        best_substring = ""
        best_window: Optional[int] = None
        for substring, window in provider_models.items():
            if substring in needle and len(substring) > len(best_substring):
                best_substring = substring
                best_window = window
        if best_window is not None:
            return best_window
    spec = PROVIDER_CATALOG.get(provider)
    if spec is not None and spec.context_window is not None:
        return spec.context_window
    return None


# Bounded message patterns for a provider's native context-length rejection.
# Matched ONLY after a structured signal, or when the message is specific enough
# that an unrelated error cannot be mistaken for overflow. Deliberately does NOT
# match "rate limit", "timeout", "unauthorized", "quota" or "429".
_OVERFLOW_CODE_HINTS = frozenset({
    "context_length_exceeded",
    "contextlengthexceeded",
    "context_window_exceeded",
    "string_above_max_length",
    "max_tokens_exceeded",
})

_OVERFLOW_MESSAGE_PATTERNS = (
    re.compile(r"maximum context length", re.IGNORECASE),
    re.compile(r"context (?:window|length)", re.IGNORECASE),
    re.compile(r"prompt is too long", re.IGNORECASE),
    re.compile(r"exceeds? the maximum number of tokens", re.IGNORECASE),
    re.compile(r"reduce the length of the messages", re.IGNORECASE),
    re.compile(r"too many tokens", re.IGNORECASE),
    re.compile(r"input token count.*exceeds", re.IGNORECASE),
)


def _structured_overflow_code(exc: BaseException) -> Optional[str]:
    """Best-effort read of a provider error's structured code, if any."""
    for attr in ("code", "error_code", "type"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            return value.lower()
    # OpenAI-compatible SDKs expose the parsed body on `.response`/`.body`.
    for attr in ("body", "response"):
        value = getattr(exc, attr, None)
        if isinstance(value, dict):
            nested = value.get("error")
            if isinstance(nested, dict) and isinstance(nested.get("code"), str):
                return nested["code"].lower()
            if isinstance(value.get("code"), str):
                return value["code"].lower()
    return None


def classify_context_overflow(exc: BaseException) -> bool:
    """True when a provider exception is a context-length rejection.

    Requires a SPECIFIC signal — a known structured error code, or a bounded
    message pattern that only a context-length error carries. An unrelated error
    (rate limit, timeout, auth, quota) returns False, so the generic classifier
    keeps its existing code. Pure; no network.
    """
    code = _structured_overflow_code(exc)
    if code and code in _OVERFLOW_CODE_HINTS:
        return True
    message = str(exc) or ""
    if not message:
        return False
    # A structured code that is present and is clearly something else means the
    # message alone must not override it.
    if code and any(hint in code for hint in ("rate", "auth", "permission", "timeout")):
        return False
    return any(pattern.search(message) for pattern in _OVERFLOW_MESSAGE_PATTERNS)


def context_overflow_error(
    provider: str, model: str, window: Optional[int], *, retried: bool = False,
) -> tuple[str, str]:
    """The honest `(code, message)` shown when overflow cannot be recovered.

    States what happened and the remedy — never a fabricated window, and it only
    claims a retry when one was actually attempted.
    """
    if window:
        detail = f"the resolved model {provider}/{model} has a {window}-token window"
    else:
        detail = f"the context window for {provider}/{model} is unknown to the runtime"
    if retried:
        action = (
            "The runtime trimmed the conversation history and retried once, but "
            "the request still did not fit."
        )
    else:
        action = "The conversation history could not be trimmed enough to fit."
    message = (
        f"The request exceeded the model's context window ({detail}). {action} "
        "Start a shorter conversation, or switch to a larger-context model."
    )
    return "CONTEXT_OVERFLOW", message


def _resolve_key(settings: ModelSettings, spec: ProviderSpec) -> Optional[str]:
    """Prefer the per-run key from the vault, then the env var, then a local default."""
    if settings.api_key:
        return settings.api_key
    if spec.env_var:
        env_value = os.environ.get(spec.env_var)
        if env_value:
            return env_value
    if spec.keyless:
        return "local"
    return None


def provider_has_credentials(provider_id: str) -> bool:
    """Whether a credential for `provider_id` is resolvable OUTSIDE the run.

    True for a keyless (local) provider, or a hosted provider whose declared env
    var holds a key. This lets a subsystem (notably vision) use a DIFFERENT
    provider's model as a fallback ONLY when the operator has actually supplied a
    credential for it — never routing to a provider the process holds no key for
    (ADR-H146 §31/§45).
    """
    spec = PROVIDER_CATALOG.get(provider_id or "")
    if spec is None:
        return False
    if spec.keyless:
        return True
    if spec.env_var and os.environ.get(spec.env_var):
        return True
    return False


def build_chat_model(settings: ModelSettings) -> Any:
    """Construct a LangChain chat model for the requested provider.

    Raises ValueError with a structured reason when the provider is unknown or
    unconfigured — the caller maps that to PROVIDER_NOT_CONFIGURED.
    """
    spec = PROVIDER_CATALOG.get(settings.provider)
    if spec is None:
        raise ValueError(f"Unknown model provider '{settings.provider}'")

    api_key = _resolve_key(settings, spec)
    temperature = settings.temperature

    if spec.kind == "openai":
        from langchain_openai import ChatOpenAI

        base_url = settings.base_url or spec.default_base_url
        model = settings.model or spec.default_model
        if not base_url:
            raise ValueError(f"Provider '{spec.id}' requires a base URL")
        if not model:
            raise ValueError(f"Provider '{spec.id}' requires a model id")
        if not api_key:
            raise ValueError(f"Provider '{spec.id}' is not configured (missing API key)")
        kwargs: dict[str, Any] = {"model": model, "base_url": base_url, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        # Token analytics require usage on the streamed response. langchain-openai
        # disables this by default when a custom base_url is set (our case for
        # every OpenAI-compatible endpoint, incl. Ollama), so a streaming run
        # would report 0 tokens and the analytics panel would be blank. Ask the
        # endpoint to include usage (standard OpenAI, Ollama and most compatible
        # servers support `stream_options.include_usage`).
        kwargs["stream_usage"] = True
        return ChatOpenAI(**kwargs)

    if spec.kind == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not api_key:
            raise ValueError("Anthropic is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatAnthropic(**kwargs)

    if spec.kind == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not api_key:
            raise ValueError("Google Gemini is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatGoogleGenerativeAI(**kwargs)

    if spec.kind == "mistral":
        from langchain_mistralai import ChatMistralAI

        if not api_key:
            raise ValueError("Mistral is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatMistralAI(**kwargs)

    if spec.kind == "groq":
        from langchain_groq import ChatGroq

        if not api_key:
            raise ValueError("Groq is not configured (missing API key)")
        kwargs = {"model": settings.model or spec.default_model, "api_key": api_key}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return ChatGroq(**kwargs)

    raise ValueError(f"Provider '{spec.id}' has unsupported kind '{spec.kind}'")


def list_providers() -> list[dict[str, Any]]:
    """Catalog for the TS side / UI — declares what can be connected.

    `models` is the declared known-model list for the picker (convenience, not
    an allowlist); `modelWindows` maps each declared model id to its resolved
    window (or None); `contextWindow` is the provider-level floor. All are
    additive and may be absent/None, so older consumers stay compatible.
    """
    providers: list[dict[str, Any]] = []
    for spec in PROVIDER_CATALOG.values():
        models = PROVIDER_MODELS.get(spec.id, ([spec.default_model] if spec.default_model else []))
        providers.append({
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "defaultBaseUrl": spec.default_base_url,
            "defaultModel": spec.default_model,
            "envVar": spec.env_var,
            "keyless": spec.keyless,
            "openaiCompatible": spec.openai_compatible,
            "dynamicDiscovery": spec.dynamic_discovery,
            "contextWindow": spec.context_window,
            "models": models,
            "modelWindows": {m: resolve_context_window(spec.id, m) for m in models},
        })
    return providers
