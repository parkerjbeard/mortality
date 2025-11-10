from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence
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
from .utils import parse_tool_arguments, to_responses_input


class OpenAIChatClient(LLMClient):
    """OpenAI Responses API client with minimal mortality-specific defaults."""

    provider = LLMProvider.OPENAI
    _SESSION_RESPONSE_KEY = "openai.previous_response_id"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is required for OpenAIChatClient")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._default_model = default_model
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
        previous_response_id = session.attributes.get(self._SESSION_RESPONSE_KEY)
        include_history = previous_response_id is None
        payload: Dict[str, Any] = {
            "model": session.config.model or self._default_model,
            "input": to_responses_input(
                session,
                messages,
                include_history=include_history,
            ),
            "temperature": session.config.temperature,
            "top_p": session.config.top_p,
        }
        if session.config.system_prompt:
            payload["instructions"] = session.config.system_prompt
        if session.config.max_output_tokens:
            payload["max_output_tokens"] = session.config.max_output_tokens
        if tools:
            payload["tools"] = list(tools)
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=v1",
        }
        response = await self._client.post(
            f"{self._base_url}/responses",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        session.attributes[self._SESSION_RESPONSE_KEY] = body.get("id")
        content = _extract_text_from_output(body)
        metadata = {
            "usage": body.get("usage"),
            "response_id": body.get("id"),
            "status": body.get("status"),
        }
        tool_calls = self._extract_tool_calls(body)
        return LLMCompletion(text=content or "", metadata=metadata, tool_calls=tool_calls)

    def _extract_tool_calls(self, body: Dict[str, Any]) -> List[LLMToolCall]:
        calls: List[LLMToolCall] = []
        output_items = body.get("output") or []
        if isinstance(output_items, list):
            for item in output_items:
                call = self._normalize_tool_call(item)
                if call:
                    calls.append(call)
        for item in body.get("tool_calls") or []:
            call = self._normalize_tool_call(item)
            if call:
                calls.append(call)
        return calls

    def _normalize_tool_call(self, item: Any) -> LLMToolCall | None:
        if not isinstance(item, dict):
            return None
        kind = item.get("type")
        if kind not in {"tool_call", "function_call"}:
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    call = self._normalize_tool_call(block)
                    if call:
                        return call
            return None
        function = item.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            args_raw = function.get("arguments")
        else:
            name = item.get("name") or item.get("tool_name")
            args_raw = item.get("arguments") or item.get("input")
        if not name:
            return None
        arguments = parse_tool_arguments(args_raw)
        return LLMToolCall(name=name, arguments=arguments, call_id=self._tool_call_id(item, function))

    def _tool_call_id(self, item: Any, function: Any) -> str | None:
        for payload in (item, function):
            if not isinstance(payload, dict):
                continue
            for key in ("id", "tool_call_id", "call_id"):
                value = payload.get(key)
                if value:
                    return str(value)
        return None


def _extract_text_from_output(body: Dict[str, Any]) -> str:
    text_chunks: List[str] = []
    output_text = body.get("output_text")
    if isinstance(output_text, list):
        text_chunks.extend(str(chunk) for chunk in output_text if isinstance(chunk, str))
    for item in body.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and "text" in part:
                text_chunks.append(str(part["text"]))
    return "".join(text_chunks)


__all__ = ["OpenAIChatClient"]
