"""DSPy LM configuration — bridges the existing LLMConfig to dspy.LM."""
import dspy
from typing import Optional
from app.llm.config import config

_lm: Optional[dspy.LM] = None

def get_dspy_lm() -> dspy.LM:
    """Lazily create and cache the dspy.LM, configured from env vars.

    The API key is NOT passed explicitly — litellm resolves it from the
    provider's expected environment variable based on the model's provider
    prefix (e.g. ``openrouter/`` -> ``OPENROUTER_API_KEY``, ``openai/`` ->
    ``OPENAI_API_KEY``, ``anthropic/`` -> ``ANTHROPIC_API_KEY``). Set
    ``LLM_MODEL`` with the appropriate provider prefix so litellm knows which
    key (and endpoint) to use.
    """
    global _lm
    if _lm is None:
        # litellm needs a provider prefix; add one if missing so it can
        # resolve the API key from the matching env var.
        if "/" in config.model:
            model_str = config.model          # already prefixed (e.g. "openrouter/...", "openai/gpt-4o")
        elif config.provider == "anthropic":
            model_str = f"anthropic/{config.model}"
        else:
            model_str = f"openai/{config.model}"  # openai + openai-compatible both use openai/ prefix

        kwargs: dict = {
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }
        # Only pass api_base for self-hosted OpenAI-compatible endpoints
        # (vLLM, Ollama). Known hosted providers (openrouter, openai,
        # anthropic) resolve their own endpoint from the provider prefix.
        if config.base_url:
            kwargs["api_base"] = config.base_url

        _lm = dspy.LM(model_str, **kwargs)
    return _lm

def ensure_dspy_configured():
    """Ensure dspy.settings has an LM. Call before running any module."""
    if dspy.settings.lm is None:
        dspy.configure(lm=get_dspy_lm())
