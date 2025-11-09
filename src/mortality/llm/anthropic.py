from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Sequence
from uuid import uuid4

from .base import (
    LLMClient,
    LLMMessage,
    LLMProvider,
    LLMSession,
    LLMSessionConfig,
    LLMStreamEvent,
    ProviderUnavailable,
)
from .utils import to_anthropic_payload

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from anthropic import AsyncAnthropic

DEFAULT_TOOL_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}}


class AnthropicMessagesClient(LLMClient):
    provider = LLMProvider.ANTHROPIC

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 30.0,
        api_version: str = "2023-06-01",
        default_max_tokens: int = 1024,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ProviderUnavailable("ANTHROPIC_API_KEY is required for AnthropicMessagesClient")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ProviderUnavailable("Install anthropic>=0.34.0 to use AnthropicMessagesClient") from exc

        headers = {"anthropic-version": api_version}
        self._client: AsyncAnthropic = AsyncAnthropic(
            api_key=self._api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=headers,
        )
        self._default_max_tokens = default_max_tokens

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

    async def stream_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[Dict[str, object]] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        system_prompt, conversation = to_anthropic_payload(session, messages)
        payload = {
            "model": session.config.model,
            "max_tokens": session.config.max_output_tokens or self._default_max_tokens,
            "temperature": session.config.temperature,
            "top_p": session.config.top_p,
            "messages": conversation,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            converted = self._convert_tools(tools)
            if converted:
                payload["tools"] = converted

        async with self._client.messages.stream(**payload) as stream:
            async for text in stream.text_stream:
                if not text:
                    continue
                yield LLMStreamEvent(type="content", content=text)

        final_message = await stream.get_final_message()
        usage = getattr(final_message, "usage", None)
        if usage is not None and hasattr(usage, "model_dump"):
            usage_payload = usage.model_dump()
        elif usage is not None and hasattr(usage, "dict"):
            usage_payload = usage.dict()
        else:
            usage_payload = usage
        metadata = {
            "stop_reason": getattr(final_message, "stop_reason", None),
            "model": getattr(final_message, "model", session.config.model),
            "usage": usage_payload,
        }
        yield LLMStreamEvent(type="end", metadata=metadata)

    def _convert_tools(self, tools: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
        """Normalize OpenAI-style tool definitions into Anthropic schema."""

        converted: List[Dict[str, object]] = []
        for tool in tools:
            if "input_schema" in tool and "name" in tool:
                converted.append(tool)
                continue
            tool_type = tool.get("type") if isinstance(tool, dict) else None
            if tool_type == "function" and isinstance(tool.get("function"), dict):
                fn = tool["function"]
                parameters = fn.get("parameters") or DEFAULT_TOOL_SCHEMA
                if not isinstance(parameters, dict):
                    parameters = DEFAULT_TOOL_SCHEMA
                converted.append(
                    {
                        "name": fn.get("name", "tool"),
                        "description": fn.get("description", ""),
                        "input_schema": parameters,
                    }
                )
        return converted


__all__ = ["AnthropicMessagesClient"]
