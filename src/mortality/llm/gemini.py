from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence
from uuid import uuid4

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
from .utils import to_gemini_contents


class GeminiChatClient(LLMClient):
    """Gemini Developer API client built on google-genai."""

    provider = LLMProvider.GEMINI

    def __init__(
        self,
        api_key: str | None = None,
        api_version: str = "v1alpha",
        default_model: str = "gemini-2.0-flash-001",
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ProviderUnavailable("GEMINI_API_KEY or GOOGLE_API_KEY is required for GeminiChatClient")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ProviderUnavailable("Install google-genai>=0.3.0 to use GeminiChatClient") from exc

        http_options = types.HttpOptions(api_version=api_version) if api_version else None
        client_kwargs: Dict[str, Any] = {"api_key": self._api_key}
        if http_options:
            client_kwargs["http_options"] = http_options
        self._client = genai.Client(**client_kwargs)
        self._types = types
        self._default_model = default_model

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

    async def complete_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[Dict[str, object]] | None = None,
    ) -> LLMCompletion:
        system_instruction, contents = to_gemini_contents(session, messages)
        config_kwargs: Dict[str, Any] = {
            "temperature": session.config.temperature,
            "top_p": session.config.top_p,
        }
        if session.config.max_output_tokens:
            config_kwargs["max_output_tokens"] = session.config.max_output_tokens
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        tool_defs = self._convert_tools(tools)
        if tool_defs:
            config_kwargs["tools"] = tool_defs
        config = self._types.GenerateContentConfig(**config_kwargs)
        model_name = session.config.model or self._default_model
        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
        text = self._response_text(response)
        metadata = self._extract_metadata(response, model_name)
        tool_calls = self._extract_tool_calls(response)
        return LLMCompletion(text=text, metadata=metadata, tool_calls=tool_calls)

    def _response_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            return "".join(str(chunk) for chunk in text)
        # Fallback to first candidate text if aggregated text is missing
        candidates = getattr(response, "candidates", None)
        if isinstance(candidates, list):
            fragments: list[str] = []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                if content is None and isinstance(candidate, dict):
                    content = candidate.get("content")
                fragments.extend(self._parts_to_text(content))
            if fragments:
                return "".join(fragments)
        return ""

    def _parts_to_text(self, content: Any) -> list[str]:
        fragments: list[str] = []
        if isinstance(content, dict):
            parts = content.get("parts")
        else:
            parts = getattr(content, "parts", None)
        if not parts:
            return fragments
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                fragments.append(str(part["text"]))
            elif hasattr(part, "text") and getattr(part, "text"):
                fragments.append(str(part.text))
        return fragments

    def _extract_metadata(self, response: Any, model_name: str) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {"model": model_name}
        usage = getattr(response, "usage_metadata", None)
        serialized = self._serialize_usage(usage)
        if serialized is not None:
            metadata["usage"] = serialized
        return metadata

    def _serialize_usage(self, usage: Any) -> Dict[str, Any] | Any | None:
        if usage is None:
            return None
        if hasattr(usage, "to_dict"):
            return usage.to_dict()
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if hasattr(usage, "__dict__"):
            return {k: v for k, v in usage.__dict__.items() if not k.startswith("_")}
        return usage

    def _convert_tools(self, tools: Sequence[Dict[str, object]] | None) -> List[Any] | None:
        if not tools:
            return None
        declarations: List[Any] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_type = tool.get("type")
            if tool_type != "function":
                continue
            fn = tool.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            description = fn.get("description")
            parameters = fn.get("parameters")
            schema = None
            if isinstance(parameters, dict):
                schema = self._types.Schema(**parameters)
            else:
                schema = self._types.Schema(type="object")
            declarations.append(
                self._types.FunctionDeclaration(
                    name=name.strip(),
                    description=description,
                    parameters=schema,
                )
            )
        if not declarations:
            return None
        return [self._types.Tool(function_declarations=declarations)]

    def _extract_tool_calls(self, response: Any) -> List[LLMToolCall]:
        calls: List[LLMToolCall] = []
        payload = getattr(response, "function_calls", None)
        if isinstance(payload, list):
            for entry in payload:
                name = getattr(entry, "name", None)
                if name is None and isinstance(entry, dict):
                    name = entry.get("name")
                if not name:
                    continue
                args = getattr(entry, "args", None)
                if args is None and isinstance(entry, dict):
                    args = entry.get("args")
                if hasattr(args, "items"):
                    arguments = dict(args)
                elif isinstance(args, dict):
                    arguments = dict(args)
                else:
                    arguments = {}
                calls.append(LLMToolCall(name=str(name), arguments=arguments))
        return calls


__all__ = ["GeminiChatClient"]
