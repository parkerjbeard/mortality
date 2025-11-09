from __future__ import annotations

from typing import Iterable

from .anthropic import AnthropicMessagesClient
from .base import ClientRegistry, ProviderUnavailable, client_registry
from .gemini import GeminiChatClient
from .grok import GrokChatClient
from .openai import OpenAIChatClient
from .openrouter import OpenRouterChatClient
from .mock import MockLLMClient


def register_default_clients(registry: ClientRegistry | None = None) -> None:
    """Best-effort registration for all upstream providers."""

    reg = registry or client_registry
    for constructor in (
        OpenAIChatClient,
        AnthropicMessagesClient,
        GrokChatClient,
        GeminiChatClient,
        OpenRouterChatClient,
        MockLLMClient,
    ):
        try:
            reg.register(constructor())
        except ProviderUnavailable:
            continue


def list_registered_providers(registry: ClientRegistry | None = None) -> Iterable[str]:
    reg = registry or client_registry
    return [provider.value for provider in reg.providers()]


__all__ = ["register_default_clients", "list_registered_providers"]
