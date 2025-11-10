from __future__ import annotations

import os
from typing import Any, Dict, Sequence
from uuid import uuid4

import httpx

from .base import LLMClient, LLMCompletion, LLMMessage, LLMProvider, LLMSession, LLMSessionConfig, ProviderUnavailable
from .utils import stringify_openai_content, to_openai_messages


class GrokChatClient(LLMClient):
    """xAI Grok-compatible chat completions client with SSE streaming."""

    provider = LLMProvider.GROK

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
        timeout: float = 60.0,
        default_model: str = "grok-4-0709",
    ) -> None:
        self._api_key = api_key or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
        if not self._api_key:
            raise ProviderUnavailable("XAI_API_KEY or GROK_API_KEY is required for GrokChatClient")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._default_model = default_model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[Dict[str, object]] | None = None,
    ) -> LLMCompletion:
        payload: Dict[str, Any] = {
            "model": session.config.model or self._default_model,
            "messages": to_openai_messages(session, messages),
            "temperature": session.config.temperature,
            "top_p": session.config.top_p,
        }
        if session.config.max_output_tokens:
            payload["max_tokens"] = session.config.max_output_tokens
        if tools:
            payload["tools"] = list(tools)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = session.config.metadata.get("request_timeout")
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout or self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        text = self._completion_text(body)
        metadata = self._extract_metadata(body)
        metadata.setdefault("model", payload["model"])
        return LLMCompletion(text=text, metadata=metadata)

    def _completion_text(self, payload: Dict[str, Any]) -> str:
        fragments: list[str] = []
        for choice in payload.get("choices", []):
            message = choice.get("message") or {}
            content = stringify_openai_content(message.get("content"))
            if content:
                fragments.append(content)
        return "".join(fragments)

    def _extract_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        for key in ("id", "model", "system_fingerprint", "created"):
            value = payload.get(key)
            if value is not None:
                metadata[key] = value
        usage = payload.get("usage")
        if usage:
            metadata["usage"] = usage
        return metadata


__all__ = ["GrokChatClient"]
