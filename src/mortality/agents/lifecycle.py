from __future__ import annotations

import asyncio
from typing import Literal, Sequence

from ..llm.base import LLMClient, LLMMessage, LLMSessionConfig, LLMStreamEvent, make_tick_tool_message
from ..telemetry.base import NullTelemetrySink, TelemetrySink
from ..mcp.bus import SharedMCPBus
from .memory import AgentMemory, DiaryEntry
from .profile import AgentProfile
from .state import AgentState, LifecycleStatus


class MortalityAgent:
    """Wraps an LLM session with mortality-aware utilities."""

    def __init__(
        self,
        client: LLMClient,
        state: AgentState,
        telemetry: TelemetrySink | None = None,
        shared_bus: SharedMCPBus | None = None,
    ) -> None:
        self._client = client
        self.state = state
        self._telemetry = telemetry or NullTelemetrySink()
        self._shared_bus = shared_bus
        self._io_lock = asyncio.Lock()

    @classmethod
    async def spawn(
        cls,
        client: LLMClient,
        profile: AgentProfile,
        memory: AgentMemory,
        session_config: LLMSessionConfig,
        telemetry: TelemetrySink | None = None,
        shared_bus: SharedMCPBus | None = None,
    ) -> "MortalityAgent":
        session = await client.create_session(session_config)
        state = AgentState(profile=profile, memory=memory, session=session)
        return cls(client=client, state=state, telemetry=telemetry, shared_bus=shared_bus)

    async def react(
        self,
        messages: Sequence[LLMMessage],
        tick_ms_left: int,
        reveal_tick_ms: bool = True,
        cause: str = "countdown",
    ) -> str:
        if self.state.status == LifecycleStatus.EXPIRED:
            raise RuntimeError(f"Agent {self.state.profile.agent_id} is already dead")
        async with self._io_lock:
            payload_ms = tick_ms_left if reveal_tick_ms else None
            tick = make_tick_tool_message(payload_ms, cause=cause)
            payload = [tick, *messages]
            for message in payload:
                self._emit_message_event("inbound", message, tick_ms_left=tick_ms_left, cause=cause)
            transcript = ""
            async for event in self._client.stream_response(self.state.session, payload):
                if event.type == "content" and event.content:
                    transcript += event.content
                    self._telemetry.emit(
                        "agent.chunk",
                        {
                            "agent_id": self.state.profile.agent_id,
                            "content_size": len(event.content),
                            "content": event.content,
                            "tick_ms_left": tick_ms_left,
                            "cause": cause,
                            "stream_ts": event.ts.isoformat(),
                        },
                    )
                elif event.type == "tool_call" and event.tool_call:
                    self._emit_tool_event("call", event, tick_ms_left=tick_ms_left, cause=cause)
                elif event.type == "tool_result":
                    self._emit_tool_event("result", event, tick_ms_left=tick_ms_left, cause=cause)
                elif event.type == "error":
                    raise RuntimeError(event.metadata.get("message", "stream error"))
            for message in payload:
                self.state.session.append(message)
            assistant_message = LLMMessage(role="assistant", content=transcript)
            self.state.session.append(assistant_message)
            self._emit_message_event("outbound", assistant_message, tick_ms_left=tick_ms_left, cause=cause)
            self.state.last_tick_ms = tick_ms_left
            return transcript

    def log_diary_entry(self, text: str, tick_ms_left: int, tags: list[str] | None = None) -> DiaryEntry:
        entry = self.state.memory.remember(text, tick_ms_left=tick_ms_left, tags=tags)
        self._telemetry.emit(
            "agent.diary_entry",
            {
                "agent_id": self.state.profile.agent_id,
                "entry": entry.model_dump(mode="json"),
            },
        )
        if self._shared_bus:
            self._shared_bus.publish_entry(self.state.profile.agent_id, entry)
        return entry

    def diary_context_message(self) -> LLMMessage | None:
        latest = self.state.memory.diary.latest()
        if not latest:
            return None
        summary = (
            f"Previous life #{latest.life_index} notes (time remaining {latest.tick_ms_left} ms):\n"
            f"{latest.text}"
        )
        return LLMMessage(role="system", content=summary)

    def record_death(self, epitaph: str = "", *, log_epitaph: bool = True) -> None:
        if log_epitaph:
            self.log_diary_entry(
                epitaph or "Fell silent.", tick_ms_left=self.state.last_tick_ms or 0, tags=["epitaph"]
            )
        self.state.mark_dead()
        self._telemetry.emit(
            "agent.death",
            {
                "agent_id": self.state.profile.agent_id,
                "last_tick_ms": self.state.last_tick_ms,
            },
        )

    def respawn(self) -> None:
        self.state.memory.start_new_life()
        self.state.respawn()
        self._telemetry.emit(
            "agent.respawn",
            {"agent_id": self.state.profile.agent_id, "life_index": self.state.memory.life_index},
        )

    def _emit_message_event(
        self,
        direction: Literal["inbound", "outbound"],
        message: LLMMessage,
        *,
        tick_ms_left: int,
        cause: str,
    ) -> None:
        self._telemetry.emit(
            "agent.message",
            {
                "agent_id": self.state.profile.agent_id,
                "direction": direction,
                "tick_ms_left": tick_ms_left,
                "cause": cause,
                "life_index": self.state.memory.life_index,
                "message": message.as_dict(),
            },
        )

    def _emit_tool_event(
        self,
        kind: Literal["call", "result"],
        event: LLMStreamEvent,
        *,
        tick_ms_left: int,
        cause: str,
    ) -> None:
        payload = {
            "agent_id": self.state.profile.agent_id,
            "kind": kind,
            "tick_ms_left": tick_ms_left,
            "cause": cause,
            "life_index": self.state.memory.life_index,
            "metadata": event.metadata,
            "event_ts": event.ts.isoformat(),
        }
        if kind == "call" and event.tool_call:
            payload["tool_call"] = {
                "name": event.tool_call.name,
                "arguments": event.tool_call.arguments,
                "ts": event.tool_call.ts.isoformat(),
            }
        if event.content:
            payload["content"] = event.content
        event_name = "agent.tool_call" if kind == "call" else "agent.tool_result"
        self._telemetry.emit(event_name, payload)


__all__ = ["MortalityAgent"]
