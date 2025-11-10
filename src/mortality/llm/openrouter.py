from __future__ import annotations
import os
from typing import Any, Dict, Sequence
from uuid import uuid4

import httpx

from .base import (
    LLMClient,
    LLMCompletion,
    LLMMessage,
    LLMProvider,
    LLMSession,
    LLMSessionConfig,
    LLMToolCall,
    ProviderUnavailable,
)
from .utils import parse_tool_arguments, stringify_openai_content, to_openai_messages


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
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

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
        referer = session.config.metadata.get("http_referer") if session.config.metadata else None
        title = session.config.metadata.get("app_title") if session.config.metadata else None
        referer = referer or self._referer
        title = title or self._app_title
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        timeout = session.config.metadata.get("request_timeout") if session.config.metadata else None
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout or self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = None
            try:
                data = exc.response.json()
                detail = data.get("error") or data
            except Exception:
                detail = exc.response.text
            message = f"OpenRouter request failed ({exc.response.status_code}) for model '{payload.get('model')}': {detail}"
            raise httpx.HTTPStatusError(message, request=exc.request, response=exc.response) from exc
        body = response.json()
        metadata = self._extract_metadata(body)
        metadata.setdefault("model", payload["model"])
        text = self._completion_text(body)
        tool_calls = self._extract_tool_calls(body)
        if not text and body.get("error"):
            raise ProviderUnavailable(f"OpenRouter returned error: {body['error']}")
        return LLMCompletion(text=text, metadata=metadata, tool_calls=tool_calls)

    def _completion_text(self, body: Dict[str, Any]) -> str:
        fragments: list[str] = []
        for choice in body.get("choices", []):
            message = choice.get("message") or {}
            content = stringify_openai_content(message.get("content"))
            if content:
                fragments.append(content)
        return "".join(fragments)

    def _extract_tool_calls(self, body: Dict[str, Any]) -> list[LLMToolCall]:
        calls: list[LLMToolCall] = []
        for choice in body.get("choices", []):
            message = choice.get("message") or {}
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                name = function.get("name") or call.get("name")
                if not name:
                    continue
                args = parse_tool_arguments(function.get("arguments"))
                calls.append(
                    LLMToolCall(name=name, arguments=args, call_id=self._tool_call_id(call))
                )
            function_call = message.get("function_call")
            if function_call:
                name = function_call.get("name")
                if name:
                    args = parse_tool_arguments(function_call.get("arguments"))
                    calls.append(
                        LLMToolCall(
                            name=name,
                            arguments=args,
                            call_id=self._tool_call_id(function_call),
                        )
                    )
        return calls

    def _tool_call_id(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("id", "tool_call_id", "call_id"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

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


__all__ = ["OpenRouterChatClient"]
