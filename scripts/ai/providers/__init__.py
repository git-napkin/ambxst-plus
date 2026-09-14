"""Provider factory."""

from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider

OPENAI_COMPAT = frozenset({"openai", "groq", "mistral", "custom", "minimax"})


def get_provider(model_spec, custom_endpoint=""):
    spec = model_spec if isinstance(model_spec, dict) else {"model": str(model_spec)}
    provider = (spec.get("provider") or "openai").lower()
    endpoint = custom_endpoint or spec.get("endpoint") or ""
    if custom_endpoint or provider in OPENAI_COMPAT:
        return OpenAIProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "ollama":
        return OllamaProvider()
    if endpoint:
        return OpenAIProvider()
    return OpenAIProvider()
