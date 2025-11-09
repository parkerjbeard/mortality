from __future__ import annotations

import json
from typing import AsyncIterator, Sequence
from uuid import uuid4

from .base import (
    LLMClient,
    LLMMessage,
    LLMStreamEvent,
    LLMSession,
    LLMSessionConfig,
    LLMProvider,
    TickToolName,
)


class MockLLMClient(LLMClient):
    """Deterministic offline client that echoes prompts for local experiments."""

    provider = LLMProvider.MOCK

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=f"mock-{uuid4().hex}", config=config)

    async def stream_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        text = self._render_response(messages)
        yield LLMStreamEvent(type="content", content=text)
        yield LLMStreamEvent(type="end")

    def _render_response(self, messages: Sequence[LLMMessage]) -> str:
        tick_ms = None
        tick_cause = "countdown"
        body = messages
        if messages and messages[0].role == "tool" and messages[0].name == TickToolName:
            payload = self._safe_json(messages[0].content)
            tick_ms = payload.get("t_ms_left")
            tick_cause = payload.get("cause", tick_cause)
            body = messages[1:]

        latest_user = next((self._normalize_content(msg.content) for msg in reversed(body) if msg.role == "user"), "")
        system_context = [
            self._normalize_content(msg.content)
            for msg in body
            if msg.role in {"system", "developer"} and msg.content
        ]

        summary_lines = []
        if tick_ms is not None:
            summary_lines.append(f"[tick {tick_ms} ms left | cause: {tick_cause}]")
        if latest_user:
            summary_lines.append(f"User focus: {self._truncate(latest_user, 240)}")
        if system_context:
            summary_lines.append(f"Context: {self._truncate(' | '.join(system_context), 240)}")
        if not summary_lines:
            summary_lines.append("Mock agent idles, no meaningful prompt received.")

        summary_lines.append("Plan: reflect, observe peers, log actionable insight.")
        return "\n".join(summary_lines)

    def _normalize_content(self, content: str | list[dict]) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content)

    def _safe_json(self, raw: str | list[dict]) -> dict:
        if isinstance(raw, list):
            return {}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return {}

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."


__all__ = ["MockLLMClient"]
