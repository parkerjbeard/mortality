from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Sequence, Tuple

from ..agents.lifecycle import MortalityAgent
from ..agents.memory import AgentMemory
from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage, LLMSessionConfig, client_registry
from ..mcp.bus import DiaryPermissionHandler, DiaryScope, SharedMCPBus
from ..mcp.permissions import AgentConsentPrompter
from ..llm.providers import register_default_clients
from ..tasks.timers import MortalityTimer, TimerEvent
from ..telemetry.base import NullTelemetrySink, TelemetrySink

TickHandler = Callable[[MortalityAgent, TimerEvent], Awaitable[None]]


class MortalityRuntime:
    """Central coordinator for agents, timers, and experiments."""

    def __init__(
        self,
        telemetry: TelemetrySink | None = None,
        auto_register_clients: bool = True,
        shared_bus: SharedMCPBus | None = None,
        permission_handler_factory: Callable[[MortalityAgent], DiaryPermissionHandler] | None = None,
    ) -> None:
        self.telemetry = telemetry or NullTelemetrySink()
        self._registry = client_registry
        if auto_register_clients:
            register_default_clients(self._registry)
        self._agents: Dict[str, MortalityAgent] = {}
        self._timers: Dict[str, MortalityTimer] = {}
        self._timer_tasks: Dict[str, asyncio.Task[None]] = {}
        self.shared_bus = shared_bus or SharedMCPBus()
        self._permission_handler_factory = permission_handler_factory or (lambda agent: AgentConsentPrompter(agent))
        self._peer_entry_digests: Dict[Tuple[str, str], str] = {}
        # Track last known ms_left per agent to enable peer-timer snapshots
        self._last_ms_left: Dict[str, int] = {}

    async def spawn_agent(
        self,
        *,
        profile: AgentProfile,
        session_config: LLMSessionConfig,
        memory: AgentMemory | None = None,
    ) -> MortalityAgent:
        client = self._registry.get(session_config.provider)
        memory = memory or AgentMemory()
        agent = await MortalityAgent.spawn(
            client=client,
            profile=profile,
            memory=memory,
            session_config=session_config,
            telemetry=self.telemetry,
            shared_bus=self.shared_bus,
        )
        self._agents[profile.agent_id] = agent
        if self.shared_bus:
            handler = self._permission_handler_factory(agent) if self._permission_handler_factory else None
            self.shared_bus.register_agent(profile=profile, handler=handler)
        self.telemetry.emit(
            "agent.spawned",
            {
                "agent_id": profile.agent_id,
                "profile": profile.model_dump(),
                "session": {
                    "provider": session_config.provider.value,
                    "model": session_config.model,
                },
            },
        )
        return agent

    def get_agent(self, agent_id: str) -> MortalityAgent:
        return self._agents[agent_id]

    def start_countdown(
        self,
        agent: MortalityAgent,
        duration: timedelta,
        tick_seconds: float,
        handler: TickHandler,
    ) -> MortalityTimer:
        timer = MortalityTimer(agent_id=agent.state.profile.agent_id, duration=duration, tick_seconds=tick_seconds)
        duration_ms = int(duration.total_seconds() * 1000)
        started_at = datetime.now(timezone.utc).isoformat()
        self.telemetry.emit(
            "timer.started",
            {
                "agent_id": agent.state.profile.agent_id,
                "duration_ms": duration_ms,
                "tick_seconds": tick_seconds,
                "started_at": started_at,
            },
        )

        async def _dispatch(event: TimerEvent) -> None:
            self.telemetry.emit(
                "timer.tick",
                {
                    "agent_id": event.agent_id,
                    "ms_left": event.ms_left,
                    "tick_index": event.tick_index,
                    "is_terminal": event.is_terminal,
                    "duration_ms": duration_ms,
                    "tick_seconds": tick_seconds,
                    "tick_ts": event.ts.isoformat(),
                },
            )
            # Update last-known ms_left for peer snapshots
            self._last_ms_left[event.agent_id] = event.ms_left
            await handler(agent, event)
            if event.is_terminal:
                self.telemetry.emit(
                    "timer.expired",
                    {
                        "agent_id": agent.state.profile.agent_id,
                        "duration_ms": duration.total_seconds() * 1000,
                        "expired_at": event.ts.isoformat(),
                    },
                )

        self._timers[agent.state.profile.agent_id] = timer
        self._timer_tasks[agent.state.profile.agent_id] = timer.start(_dispatch)
        return timer

    async def peer_diary_messages(
        self,
        *,
        requestor_id: str,
        owners: Sequence[str] | None = None,
        limit_per_owner: int = 1,
        reason: str = "",
    ) -> list[LLMMessage]:
        if not self.shared_bus:
            return []
        scope = DiaryScope(limit=limit_per_owner)
        resources = await self.shared_bus.fetch_resources(
            requestor_id=requestor_id,
            owners=owners,
            scope=scope,
            reason=reason,
        )
        messages: list[LLMMessage] = []
        for resource in resources:
            if not resource.entries:
                continue
            key = (requestor_id, resource.owner_id)
            digest = json.dumps(resource.entries, sort_keys=True)
            if self._peer_entry_digests.get(key) == digest:
                continue
            self._peer_entry_digests[key] = digest
            messages.append(resource.to_message())
        return messages

    async def shutdown(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        await asyncio.gather(*(task for task in self._timer_tasks.values()), return_exceptions=True)
        self._agents.clear()
        self._timers.clear()
        self._timer_tasks.clear()
        await self._close_registered_clients()

    def snapshot_diaries(self) -> Dict[str, list[Dict[str, Any]]]:
        """Return the current diary entries for all spawned agents."""

        snapshot: Dict[str, list[Dict[str, Any]]] = {}
        for agent_id, agent in self._agents.items():
            snapshot[agent_id] = agent.state.memory.diary.serialize()
        return snapshot

    def peer_timer_snapshot(self, *, exclude_agent_id: str | None = None) -> Dict[str, int | None]:
        """Return last-known ms_left for all agents (None if unknown)."""
        snapshot: Dict[str, int | None] = {}
        for agent_id in self._agents.keys():
            if exclude_agent_id and agent_id == exclude_agent_id:
                continue
            snapshot[agent_id] = self._last_ms_left.get(agent_id)
        return snapshot

    def snapshot_agent_routes(self) -> Dict[str, Dict[str, Any]]:
        """Return per-agent routed model history (if any)."""

        snapshot: Dict[str, Dict[str, Any]] = {}
        for agent_id, agent in self._agents.items():
            attrs = agent.state.session.attributes
            history = list(attrs.get("routed_models", []))
            last = attrs.get("last_routed_model")
            if not history and not last:
                continue
            snapshot[agent_id] = {
                "history": history,
                "last": last or (history[-1] if history else None),
            }
        return snapshot

    async def _close_registered_clients(self) -> None:
        closers = []
        for client in self._registry.clients():
            closer = getattr(client, "aclose", None)
            if closer:
                result = closer()
                if asyncio.iscoroutine(result):
                    closers.append(result)
        if closers:
            await asyncio.gather(*closers, return_exceptions=True)


__all__ = ["MortalityRuntime"]
