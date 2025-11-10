from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Literal, MutableMapping, Optional, Protocol, Sequence

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Supported upstream LLM vendors."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROK = "grok"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    MOCK = "mock"


RoleLiteral = Literal["system", "user", "assistant", "tool", "developer"]


class LLMMessage(BaseModel):
    """Unified chat message model across providers."""

    role: RoleLiteral
    content: str | List[Dict[str, Any]]
    name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.metadata:
            payload["metadata"] = self.metadata
        payload["ts"] = self.ts.isoformat()
        return payload


class LLMToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMStreamEvent(BaseModel):
    """Streaming token/tool events emitted by a model provider."""

    type: Literal["content", "tool_call", "tool_result", "session", "error", "end"]
    content: Optional[str] = None
    tool_call: Optional[LLMToolCall] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMSessionConfig(BaseModel):
    """Provider-agnostic session knobs."""

    provider: LLMProvider
    model: str
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9
    max_output_tokens: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class LLMSession:
    """Represents an active conversation with a provider."""

    id: str
    config: LLMSessionConfig
    history: List[LLMMessage] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def append(self, message: LLMMessage) -> None:
        self.history.append(message)


class LLMClient(Protocol):
    """Minimal interface every provider client must implement."""

    provider: LLMProvider

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:  # pragma: no cover - interface
        ...

    async def stream_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> AsyncIterator[LLMStreamEvent]:  # pragma: no cover - interface
        ...


TickToolName = "mortality.tick"


def make_tick_tool_message(ms_left: int, cause: str = "countdown") -> LLMMessage:
    """Encode a timer tick as a tool message for every provider."""

    payload = {"t_ms_left": ms_left, "cause": cause}
    return LLMMessage(role="tool", name=TickToolName, content=json.dumps(payload))


class ClientRegistry:
    """Registry for dynamically selected provider clients."""

    def __init__(self) -> None:
        self._clients: MutableMapping[LLMProvider, LLMClient] = {}

    def register(self, client: LLMClient) -> None:
        self._clients[client.provider] = client

    def get(self, provider: LLMProvider) -> LLMClient:
        if provider not in self._clients:
            raise KeyError(f"Client for provider {provider.value} is not registered")
        return self._clients[provider]

    def providers(self) -> List[LLMProvider]:
        return list(self._clients.keys())

    def clients(self) -> List[LLMClient]:
        return list(self._clients.values())


client_registry = ClientRegistry()


class ProviderUnavailable(RuntimeError):
    pass
