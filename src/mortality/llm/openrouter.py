from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Dict, Iterable, Sequence
from uuid import uuid4

import httpx

from .base import (
    LLMClient,
    LLMMessage,
    LLMProvider,
    LLMSession,
    LLMSessionConfig,
    LLMStreamEvent,
    ProviderUnavailable,
)
from .utils import stringify_openai_content, to_openai_messages


class OpenRouterChatClient(LLMClient):
    """OpenRouter chat completions client with SSE streaming."""

    provider = LLMProvider.OPENROUTER

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
        default_model: str = "openrouter/auto",
        referer: str | None = None,
        app_title: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ProviderUnavailable("OPENROUTER_API_KEY is required for OpenRouterChatClient")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._default_model = default_model
        self._referer = referer or os.getenv("OPENROUTER_HTTP_REFERER")
        self._app_title = app_title or os.getenv("OPENROUTER_APP_TITLE")

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

    async def stream_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[Dict[str, object]] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        payload: Dict[str, Any] = {
            "model": session.config.model or self._default_model,
            "messages": to_openai_messages(session, messages),
            "temperature": session.config.temperature,
            "top_p": session.config.top_p,
            "stream": True,
        }
        if session.config.max_output_tokens:
            payload["max_tokens"] = session.config.max_output_tokens
        if tools:
            payload["tools"] = list(tools)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        referer = session.config.metadata.get("http_referer") if session.config.metadata else None
        title = session.config.metadata.get("app_title") if session.config.metadata else None
        referer = referer or self._referer
        title = title or self._app_title
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        timeout = session.config.metadata.get("request_timeout") if session.config.metadata else None
        last_metadata: Dict[str, Any] = {"model": payload["model"]}
        async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:]
                    chunk_raw = line.strip()
                    if not chunk_raw:
                        continue
                    if chunk_raw == "[DONE]":
                        break
                    chunk = self._parse_chunk(chunk_raw)
                    if chunk is None:
                        continue
                    if error := chunk.get("error"):
                        metadata = {"code": error.get("code")} if isinstance(error, dict) else {}
                        yield LLMStreamEvent(
                            type="error",
                            content=json.dumps(error) if isinstance(error, dict) else str(error),
                            metadata=metadata,
                        )
                        continue
                    chunk_meta = self._extract_chunk_metadata(chunk)
                    if chunk_meta:
                        last_metadata.update(chunk_meta)
                    for event in self._chunk_events(chunk, chunk_meta):
                        yield event
        yield LLMStreamEvent(type="end", metadata=last_metadata)

    def _parse_chunk(self, payload: str) -> Dict[str, Any] | None:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def _chunk_events(self, chunk: Dict[str, Any], metadata: Dict[str, Any]) -> Iterable[LLMStreamEvent]:
        for choice in chunk.get("choices", []):
            finish_reason = choice.get("finish_reason")
            delta = choice.get("delta") or {}
            content = stringify_openai_content(delta.get("content"))
            if not content:
                message = choice.get("message", {})
                content = stringify_openai_content(message.get("content"))
            if not content:
                continue
            event_meta = dict(metadata)
            if finish_reason:
                event_meta["finish_reason"] = finish_reason
            if delta.get("role"):
                event_meta["role"] = delta["role"]
            if choice.get("index") is not None:
                event_meta["choice_index"] = choice["index"]
            yield LLMStreamEvent(type="content", content=content, metadata=event_meta)

    def _extract_chunk_metadata(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in ("id", "model", "system_fingerprint", "created"):
            value = chunk.get(key)
            if value is not None:
                metadata[key] = value
        usage = chunk.get("usage")
        if usage:
            metadata["usage"] = usage
        return metadata


__all__ = ["OpenRouterChatClient"]
