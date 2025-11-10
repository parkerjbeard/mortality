"""Mortality: time-aware multi-agent experiment framework.

Loads environment variables from a local `.env` file if present so SDK/API
clients (OpenRouter, OpenAI, Anthropic, xAI/Grok, Gemini) pick up keys
without extra user plumbing.
"""

# Best-effort .env loading (does nothing if python-dotenv is missing)
try:  # pragma: no cover - side-effect convenience
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 - ignore missing dotenv or any load issues
    pass

from .experiments.registry import ExperimentRegistry
from .orchestration.runtime import MortalityRuntime

__all__ = [
    "ExperimentRegistry",
    "MortalityRuntime",
]
