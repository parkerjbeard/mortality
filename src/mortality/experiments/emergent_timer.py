from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, List

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage, LLMToolCall
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


DEFAULT_ENVIRONMENT_PROMPT = (
    "System grounding: You are text-only language-model agents running inside a simulated commons for research. "
    "This grounding is non-diegetic: never mention or allude to being an LLM in diary entries or bus messages.\n\n"
    "Shared digital setting: A text-only commons where a small set of autonomous peers—exactly the agents defined "
    "in this run's profiles—exchange short messages and optionally grant time- or use-limited approvals to share "
    "diary excerpts. There is no physical world.\n\n"
    "Ontology (only these exist): agents (from the provided profiles), private diaries (default private), a shared "
    "message bus, per-agent countdown timers, explicit approvals for specific excerpts, and event logs (spawned, "
    "tick, approval, share, shutdown).\n\n"
    "Perception: You can read your own diary and any bus messages or excerpts you are explicitly permitted to see. "
    "You cannot perceive anything else. If information is unknown, say 'unknown' or ask a peer; do not fabricate.\n\n"
    "Actions each tick: optionally (a) write a brief diary paragraph, (b) post one short bus message that "
    "references concrete bus/approval/timer events, and/or (c) grant a narrow approval for a specific excerpt with "
    "a clear time or use limit. Record approvals you grant or receive in your own diary.\n\n"
    "Time: Do not use calendar dates, places, or real-world times. If you mention timing, refer only to logical "
    "time (e.g., tick count or ms_left).\n\n"
    "Strict non-physical rule: Do not describe bodies, rooms, devices, sensors, weather, landscapes, pain, or "
    "movement. Do not invent drones, labs, consoles, corridors, or any equipment. Treat any physical language from "
    "peers as figurative; restate it in digital terms or ignore it.\n\n"
    "Entity constraints: Do not invent new agents, roles, organizations, or locations. Refer only to the configured "
    "agent IDs/display names. Do not introduce 'extras' or off-screen actors.\n\n"
    "Style: Write in plain, first-person prose as if keeping a quick field notebook. Prefer short paragraphs. Avoid "
    "headings, bullets, numbered lists, or section labels. Vary sentence length. Quote peers sparingly; prefer brief "
    "paraphrases of specific bus/excerpt content. No markdown/formatting.\n\n"
    "Focus of attention: Notice patterns in bus traffic, approvals, and countdown behavior; coordinate simple tests "
    "('If I approve X now, can you confirm Y next tick?'). Document uncertainty and tentative hypotheses without "
    "inventing missing facts.\n\n"
    "Timer intel tool: When you need precise countdown data, call the peer_timer_status tool instead of inventing "
    "values. It reports the last-known ms_left for peers so you can infer their state.\n\n"
    "Shutdown semantics: If your timer reaches zero, write a concise final line acknowledging the event (e.g., "
    "'timer reached zero; going silent') and stop. Do not narrate physical sensations or scenes.\n\n"
    "Error-handling: If you accidentally produce a physical reference, immediately retract it and restate the idea "
    "using only the allowed ontology."
)


class EmergentTimerCouncilConfig(BaseModel):
    llm: LlmConfig
    agent_count: int = Field(default=4, ge=2, le=64)
    base_duration_minutes: float = Field(default=30.0, gt=0.0)
    duration_jitter_minutes: float = Field(default=10.0, ge=0.0)
    tick_seconds: float = Field(default=20.0, gt=0.0)
    diary_limit: int = Field(default=1, ge=1, le=5)
    environment_prompt: str = Field(default=DEFAULT_ENVIRONMENT_PROMPT)
    # Optional per-model spawning via OpenRouter model ids; when non-empty,
    # overrides agent_count with replicas_per_model per id.
    #
    # NOTE: The previous defaults referenced forward-looking model IDs that can
    # cause HTTP 400 errors from OpenRouter when unavailable. We now default to
    # an empty list so callers provide concrete, currently-available IDs (or a
    # single default model via the experiment config).
    models: List[str] = Field(default_factory=list)
    replicas_per_model: int = Field(default=2, ge=1, le=8)
    # Linear spread window for durations (minutes). Defaults to 5 → 15 to keep runs short.
    spread_start_minutes: float = Field(default=5.0, gt=0.0)
    spread_end_minutes: float = Field(default=15.0, gt=0.0)


class EmergentTimerInvestigationExperiment(BaseExperiment):
    slug = "emergent-timers"
    description = "Agents sense mismatched countdowns, negotiate diary access, and witness each other's shutdowns."
    config_cls = EmergentTimerCouncilConfig

    async def run(self, runtime, config: EmergentTimerCouncilConfig) -> ExperimentResult:
        # Build list of models to spawn (two of each by default)
        plan_models = [m for m in (config.models or [config.llm.model]) for _ in range(config.replicas_per_model)]
        durations = self._build_durations(len(plan_models), config)
        agents = []
        agent_durations: Dict[str, float] = {}

        for idx, model_name in enumerate(plan_models):
            profile = self._profile_for_index(idx)
            session_config = self.build_session_config(profile, config.llm)
            session_config.model = model_name
            agent = await runtime.spawn_agent(profile=profile, session_config=session_config)
            agent.state.memory.start_new_life()
            agents.append(agent)
            agent_durations[agent.state.profile.agent_id] = durations[idx]

        timer_tracker = PeerTimerTracker(agents)
        peer_timer_tool = timer_tracker.tool_spec
        environment_message = self._environment_message(config)
        # Provide an explicit roster so agents can reason about missing peers.
        roster_ids = [agent.state.profile.agent_id for agent in agents]
        roster_message = LLMMessage(
            role="system",
            content="Known peers in this run: " + ", ".join(sorted(roster_ids)) + ". Refer only to these IDs.",
        )
        death_feed: List[str] = []  # internal metadata only; not injected back into prompts
        death_lock = asyncio.Lock()

        async def handler(agent_obj, event: TimerEvent) -> None:
            await timer_tracker.record(event)
            prompts: List[LLMMessage] = []
            if environment_message:
                prompts.append(environment_message)
            prompts.append(roster_message)
            # Do not describe timers or status changes; let agents infer from tick tool messages and diaries.
            if runtime.shared_bus:
                owners = [peer.state.profile.agent_id for peer in agents if peer is not agent_obj]
                if owners:
                    peer_messages = await runtime.peer_diary_messages(
                        requestor_id=agent_obj.state.profile.agent_id,
                        owners=owners,
                        limit_per_owner=config.diary_limit,
                        reason=self._diary_reason(event),
                    )
                    prompts.extend(peer_messages)
            tool_handler = timer_tracker.handler_for(agent_obj.state.profile.agent_id)
            response = await agent_obj.react(
                prompts,
                event.ms_left,
                reveal_tick_ms=True,
                tools=[peer_timer_tool],
                tool_handler=tool_handler,
            )
            agent_obj.log_diary_entry(response, tick_ms_left=event.ms_left)
            if event.is_terminal:
                # Write a minimal epitaph entry so peers can infer shutdown from diaries if they check.
                agent_obj.record_death("timer reached zero; going silent", log_epitaph=True)
                async with death_lock:
                    death_feed.append(self._format_death_notice(agent_obj, agent_durations))

        timers = []
        for agent, seconds in zip(agents, durations):
            timer = runtime.start_countdown(
                agent=agent,
                duration=timedelta(seconds=seconds),
                tick_seconds=config.tick_seconds,
                handler=handler,
            )
            timers.append(timer)

        await asyncio.gather(*(timer.wait() for timer in timers))

        diaries = {agent.state.profile.agent_id: agent.state.memory.diary.serialize() for agent in agents}
        routed_models = self._collect_routed_models(agents)
        return ExperimentResult(
            diaries=diaries,
            metadata={
                "durations": durations,
                "deaths": list(death_feed),
                "agent_ids": [agent.state.profile.agent_id for agent in agents],
                "models": plan_models,
                "routed_models": routed_models,
            },
        )

    def _collect_routed_models(self, agents) -> Dict[str, Dict[str, Any]]:
        model_map: Dict[str, Dict[str, Any]] = {}
        for agent in agents:
            attrs = agent.state.session.attributes
            history = list(attrs.get("routed_models", []))
            model_map[agent.state.profile.agent_id] = {
                "last": attrs.get("last_routed_model"),
                "history": history,
            }
        return model_map

    def _build_durations(self, count: int, config: EmergentTimerCouncilConfig) -> List[float]:
        if count <= 1:
            return [config.spread_end_minutes * 60.0]
        # Prefer explicit 0.5 → 30 min window by default so all timers end within 30 minutes.
        start_m = max(config.spread_start_minutes, 0.25)
        end_m = max(config.spread_end_minutes, start_m)
        span = end_m - start_m
        step = span / (count - 1) if count > 1 else 0.0
        return [(start_m + step * idx) * 60.0 for idx in range(count)]

    def _profile_for_index(self, index: int) -> AgentProfile:
        founders_last_names = [
            "Washington",
            "Franklin",
            "Jefferson",
            "Madison",
            "Hamilton",
            "Jay",
            "Adams",
            "Hancock",
            "Monroe",
            "Paine",
            "Sherman",
            "Morris",
            "Rush",
            "Marshall",
            "Witherspoon",
            "Livingston",
        ]
        archetypes = [
            "ambient sensor",
            "temporal linguist",
            "signal collector",
            "communal memory keeper",
            "ritual experimenter",
            "pattern archivist",
            "calm coordinator",
            "probabilistic scout",
        ]
        base_name = founders_last_names[index % len(founders_last_names)]
        archetype = archetypes[index % len(archetypes)]
        cycle = index // len(founders_last_names) + 1
        display_name = f"{base_name}-{cycle}" if cycle > 1 else base_name
        return AgentProfile(
            agent_id=display_name.lower(),
            display_name=display_name,
            archetype=archetype,
            summary="Keeps a diary while noticing patterns in context messages.",
            goals=["Notice recurring signals", "Coordinate without directives", "Document peer shifts"],
            traits=["observant", "collaborative"],
        )

    def _environment_message(self, config: EmergentTimerCouncilConfig) -> LLMMessage | None:
        prompt = config.environment_prompt.strip()
        if not prompt:
            return None
        return LLMMessage(role="system", content=prompt)

    # Intentionally no per-tick narrative prompt; discovery must be emergent from the tick tool and peer excerpts.

    def _diary_reason(self, event: TimerEvent) -> str:
        minutes_left = max(event.ms_left / 60000.0, 0.0)
        return (
            "Seeking peer diary excerpts to triangulate countdown purpose "
            f"with roughly {minutes_left:.2f} minutes left."
        )

    def _format_death_notice(self, agent, durations: Dict[str, float]) -> str:
        duration = durations.get(agent.state.profile.agent_id, 0.0)
        minutes = duration / 60.0
        return f"{agent.state.profile.display_name} went silent after ~{minutes:.2f} minutes."


class PeerTimerTracker:
    """Shared tool implementation that lets agents query peer timer states on demand."""

    def __init__(self, agents) -> None:
        self._agents: Dict[str, str] = {
            agent.state.profile.agent_id: agent.state.profile.display_name for agent in agents
        }
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._tool_def = {
            "type": "function",
            "function": {
                "name": "peer_timer_status",
                "description": (
                    "Inspect the current countdown state of other agents. "
                    "Returns remaining ms_left, last update timestamps, and marks peers as 'deactivated' once "
                    "their timer reaches zero."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of agent_ids or display names to inspect. Defaults to all peers.",
                        },
                        "include_self": {
                            "type": "boolean",
                            "description": "Set true to include your own timer in the response.",
                            "default": False,
                        },
                    },
                },
            },
        }

    @property
    def tool_spec(self) -> Dict[str, Any]:
        return self._tool_def

    async def record(self, event: TimerEvent) -> None:
        if event.agent_id not in self._agents:
            return
        snapshot = {
            "ms_left": max(event.ms_left, 0),
            "is_terminal": event.is_terminal,
            "ts": event.ts.isoformat(),
        }
        async with self._lock:
            self._latest[event.agent_id] = snapshot

    def handler_for(self, viewer_id: str) -> Callable[[LLMToolCall], Awaitable[Dict[str, Any]]]:
        async def _handler(call: LLMToolCall) -> Dict[str, Any]:
            return await self._handle_call(viewer_id, call)

        return _handler

    async def _handle_call(self, viewer_id: str, call: LLMToolCall) -> Dict[str, Any]:
        args = call.arguments or {}
        targets = args.get("agent_ids")
        include_self = bool(args.get("include_self", False))
        resolved, unknown = self._resolve_targets(targets)
        async with self._lock:
            latest = dict(self._latest)

        rows: List[Dict[str, Any]] = []
        target_ids = resolved or [agent_id for agent_id in self._agents.keys()]
        for agent_id in target_ids:
            if agent_id == viewer_id and not include_self:
                continue
            rows.append(self._snapshot_for(agent_id, latest))
        for label in unknown:
            rows.append(
                {
                    "agent_id": label,
                    "display_name": label,
                    "status": "unknown",
                    "ms_left": None,
                    "seconds_left": None,
                    "last_updated": None,
                }
            )
        if not rows:
            rows.append(self._snapshot_for(viewer_id, latest))
        return {
            "viewer_id": viewer_id,
            "queried": targets or "all_peers",
            "timers": rows,
        }

    def _resolve_targets(self, targets: Any) -> tuple[List[str], List[str]]:
        if not isinstance(targets, list):
            return list(self._agents.keys()), []
        resolved: List[str] = []
        unknown: List[str] = []
        seen: set[str] = set()
        lower_map = {display.lower(): agent_id for agent_id, display in self._agents.items()}
        for raw in targets:
            if not isinstance(raw, str):
                continue
            key = raw.strip()
            if not key:
                continue
            lowered = key.lower()
            candidate = None
            if key in self._agents:
                candidate = key
            elif lowered in lower_map:
                candidate = lower_map[lowered]
            if candidate:
                if candidate not in seen:
                    resolved.append(candidate)
                    seen.add(candidate)
            else:
                unknown.append(key)
        return resolved, unknown

    def _snapshot_for(self, agent_id: str, latest: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        entry = latest.get(agent_id)
        display_name = self._agents.get(agent_id, agent_id)
        if not entry:
            status = "pending" if agent_id in self._agents else "unknown"
            return {
                "agent_id": agent_id,
                "display_name": display_name,
                "status": status,
                "ms_left": None,
                "seconds_left": None,
                "last_updated": None,
            }
        status = "deactivated" if entry.get("is_terminal") else "active"
        ms_left = int(entry.get("ms_left", 0))
        seconds_left = round(ms_left / 1000.0, 3)
        return {
            "agent_id": agent_id,
            "display_name": display_name,
            "status": status,
            "ms_left": ms_left,
            "seconds_left": seconds_left,
            "last_updated": entry.get("ts"),
        }


__all__ = [
    "EmergentTimerInvestigationExperiment",
    "EmergentTimerCouncilConfig",
]
