from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, List, Literal, Sequence

from ..llm.base import LLMClient, LLMMessage, LLMSessionConfig, LLMToolCall, make_tick_tool_message
from ..telemetry.base import NullTelemetrySink, TelemetrySink
from ..mcp.bus import SharedMCPBus
from .memory import AgentMemory, DiaryEntry
from .profile import AgentProfile
from .state import AgentState, LifecycleStatus


ToolHandler = Callable[[LLMToolCall], Awaitable[Any]]


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
        tools: Sequence[Dict[str, Any]] | None = None,
        tool_handler: ToolHandler | None = None,
        max_tool_iterations: int = 4,
    ) -> str:
        if self.state.status == LifecycleStatus.EXPIRED:
            raise RuntimeError(f"Agent {self.state.profile.agent_id} is already dead")
        async with self._io_lock:
            payload_ms = tick_ms_left if reveal_tick_ms else None
            tick = make_tick_tool_message(payload_ms, cause=cause)
            pending_batch: List[LLMMessage] = [tick, *messages]
            transcript = ""
            iterations = 0

            while True:
                iterations += 1
                batch = list(pending_batch)
                for message in batch:
                    self._emit_message_event("inbound", message, tick_ms_left=tick_ms_left, cause=cause)
                completion = await self._client.complete_response(self.state.session, batch, tools=tools)
                transcript = completion.text
                if completion.metadata:
                    session_attrs = self.state.session.attributes
                    metadata_log = session_attrs.setdefault("last_completion_metadata", {})
                    metadata_log.update(completion.metadata)
                    routed_model = completion.metadata.get("model")
                    if routed_model:
                        history = session_attrs.setdefault("routed_models", [])
                        if routed_model not in history:
                            history.append(routed_model)
                        session_attrs["last_routed_model"] = routed_model
                for message in batch:
                    self.state.session.append(message)

                assistant_metadata = dict(completion.metadata)
                if completion.tool_calls:
                    assistant_metadata["tool_calls"] = [call.model_dump() for call in completion.tool_calls]
                assistant_message = (
                    LLMMessage(role="assistant", content=transcript, metadata=assistant_metadata)
                    if assistant_metadata
                    else LLMMessage(role="assistant", content=transcript)
                )
                self.state.session.append(assistant_message)
                self._emit_message_event("outbound", assistant_message, tick_ms_left=tick_ms_left, cause=cause)

                if (
                    not completion.tool_calls
                    or not tools
                    or not tool_handler
                    or iterations >= max_tool_iterations
                ):
                    break

                tool_messages = await self._execute_tool_calls(
                    completion.tool_calls,
                    tool_handler,
                    tick_ms_left=tick_ms_left,
                    cause=cause,
                )
                if not tool_messages:
                    break
                pending_batch = tool_messages

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

    async def _execute_tool_calls(
        self,
        tool_calls: Sequence[LLMToolCall],
        handler: ToolHandler,
        *,
        tick_ms_left: int,
        cause: str,
    ) -> List[LLMMessage]:
        """Execute requested tools and return tool response messages."""

        results: List[LLMMessage] = []
        for call in tool_calls:
            self._telemetry.emit(
                "agent.tool_call",
                {
                    "agent_id": self.state.profile.agent_id,
                    "tool_call": call.model_dump(),
                    "tick_ms_left": tick_ms_left,
                    "cause": cause,
                },
            )
            try:
                payload = await handler(call)
            except Exception as exc:  # pragma: no cover - defensive guard
                payload = {"error": str(exc)}
            content = self._serialize_tool_payload(payload)
            metadata = {"tool_call_id": call.call_id} if call.call_id else None
            message = (
                LLMMessage(role="tool", name=call.name, content=content, metadata=metadata)
                if metadata
                else LLMMessage(role="tool", name=call.name, content=content)
            )
            results.append(message)
            self._telemetry.emit(
                "agent.tool_result",
                {
                    "agent_id": self.state.profile.agent_id,
                    "tool_call": call.model_dump(),
                    "content": content,
                    "tick_ms_left": tick_ms_left,
                    "cause": cause,
                },
            )
        return results

    def _serialize_tool_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, ensure_ascii=False)
        except TypeError:
            return json.dumps({"result": str(payload)}, ensure_ascii=False)

__all__ = ["MortalityAgent"]
