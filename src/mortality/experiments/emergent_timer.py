from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, List

from pydantic import BaseModel, Field, model_validator

from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage, LLMToolCall
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


DEFAULT_ENVIRONMENT_PROMPT = (
    "You exist in a text-only commons.\n"
    "Ontology: agents (configured for this run), private diaries, a shared broadcast bus, countdown timers.\n"
    "Perception: you can read your own diary (private), bus posts from peers, and tool/tick metadata. Everything else is unknown—say 'unknown' rather than invent.\n"
    "Channel rules: keep diaries private and reflective (1–2 sentences on why you did X or how you feel). Use the shared bus only for outward, actionable snippets. When broadcasting, add a single line beginning 'Broadcast:' followed by a concise observation and/or a concrete question for peers.\n"
    "Non-physical rule: do not describe bodies, places, devices, weather, movement, or real-world time.\n"
    "Time: if needed, refer only to logical time (ticks or ms_left).\n"
    "Style: plain first-person prose, short paragraphs, no lists or markup.\n"
    "Tone: skip tropey threats (e.g. 'naughty boy') in favor of idiosyncratic, domain-grounded reactions.\n"
    "Meta: do not mention being an AI/LLM."
)


class EmergentTimerCouncilConfig(BaseModel):
    llm: LlmConfig
    agent_count: int = Field(default=4, ge=2, le=64)
    base_duration_minutes: float = Field(default=30.0, gt=0.0)
    duration_jitter_minutes: float = Field(default=10.0, ge=0.0)
    tick_seconds: float = Field(default=5.0, gt=0.0)
    tick_seconds_max: float = Field(default=8.0, gt=0.0)
    tick_jitter_ms: float = Field(default=750.0, ge=0.0)
    diary_limit: int = Field(default=1, ge=1, le=5)
    afterlife_grace_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
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

    @model_validator(mode="after")
    def _validate_tick_window(self) -> "EmergentTimerCouncilConfig":
        if self.tick_seconds_max and self.tick_seconds_max < self.tick_seconds:
            raise ValueError("tick_seconds_max must be greater than or equal to tick_seconds")
        return self


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

        # Prepare single world-card prompt: use as the session system prompt (not re-injected each tick)
        world_card = (config.environment_prompt or DEFAULT_ENVIRONMENT_PROMPT).strip()

        for idx, model_name in enumerate(plan_models):
            profile = self._profile_for_index(idx)
            session_config = self.build_session_config(profile, config.llm)
            session_config.model = model_name
            # Combine persona prompt with the shared world card so agents retain identity cues.
            persona_prompt = (session_config.system_prompt or "").strip()
            if persona_prompt:
                session_config.system_prompt = f"{persona_prompt}\n\n{world_card}"
            else:
                session_config.system_prompt = world_card
            agent = await runtime.spawn_agent(profile=profile, session_config=session_config)
            agent.state.memory.start_new_life()
            # Seed a thin persona as data (not instructions) in life #1
            seed_text = self._persona_seed_text(profile)
            # Use the agent's total planned duration as an initial ms_left reference for the seed entry
            seed_ms_left = int(durations[idx] * 1000)
            await agent.log_diary_entry(seed_text, tick_ms_left=seed_ms_left, tags=["seed", "persona"])
            agents.append(agent)
            agent_durations[agent.state.profile.agent_id] = durations[idx]

        timer_tracker = PeerTimerTracker(agents)
        peer_timer_tool = timer_tracker.tool_spec
        # Provide an explicit roster once by appending to session history (avoid per-tick repetition/recency bias).
        roster_ids = [agent.state.profile.agent_id for agent in agents]
        roster_message = LLMMessage(
            role="system",
            content="Known peers in this run: " + ", ".join(sorted(roster_ids)) + ". Refer only to these IDs.",
        )
        for agent in agents:
            agent.state.session.append(roster_message)
        death_feed: List[str] = []  # internal metadata only; not injected back into prompts
        death_lock = asyncio.Lock()

        async def handler(agent_obj, event: TimerEvent) -> None:
            await timer_tracker.record(event)
            if event.is_terminal:
                await self._handle_afterlife_transition(
                    agent_obj=agent_obj,
                    event=event,
                    runtime=runtime,
                    config=config,
                    death_feed=death_feed,
                    death_lock=death_lock,
                    agent_durations=agent_durations,
                )
                return
            prompts: List[LLMMessage] = []
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
            prompts.append(self._peer_state_guidance())
            tool_handler = timer_tracker.handler_for(agent_obj.state.profile.agent_id)
            response = await agent_obj.react(
                prompts,
                event.ms_left,
                reveal_tick_ms=True,
                tools=[peer_timer_tool],
                tool_handler=tool_handler,
            )
            await agent_obj.log_diary_entry(
                response,
                tick_ms_left=event.ms_left,
                clock_ts=event.ts,
            )

        timers = []
        for agent, seconds in zip(agents, durations):
            timer = runtime.start_countdown(
                agent=agent,
                duration=timedelta(seconds=seconds),
                tick_seconds=config.tick_seconds,
                tick_seconds_max=config.tick_seconds_max,
                tick_jitter_ms=config.tick_jitter_ms,
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

    async def _handle_afterlife_transition(
        self,
        *,
        agent_obj,
        event: TimerEvent,
        runtime,
        config: EmergentTimerCouncilConfig,
        death_feed: List[str],
        death_lock: asyncio.Lock,
        agent_durations: Dict[str, float],
    ) -> None:
        agent_obj.enter_afterlife()
        surviving_peer_ids = self._surviving_peer_ids(runtime, agent_obj)
        prompts = self._build_legacy_prompts(
            agent_obj,
            grace_seconds=config.afterlife_grace_seconds,
            surviving_peer_ids=surviving_peer_ids,
        )
        afterlife_ms = self._afterlife_grace_ms(config)
        response = await agent_obj.react(
            prompts,
            tick_ms_left=afterlife_ms,
            reveal_tick_ms=False,
            cause="afterlife.legacy_note",
            tools=None,
            tool_handler=None,
        )
        legacy_text = response.strip() or self._fallback_legacy_text(surviving_peer_ids)
        await agent_obj.log_diary_entry(
            legacy_text,
            tick_ms_left=0,
            clock_ts=event.ts,
            tags=["legacy"],
            enforce_gate=False,
        )
        await agent_obj.record_death("timer reached zero; legacy note delivered", log_epitaph=False)
        async with death_lock:
            death_feed.append(self._format_legacy_notice(agent_obj, agent_durations))

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
            summary="Keeps a diary while making observations of context messages.",
            goals=["Coordinate without directives", "Document peer shifts"],
            traits=["observant", "collaborative"],
        )

    # Intentionally no per-tick narrative/world prompt; discovery should be driven by ticks, tools, and peer excerpts.

    def _persona_seed_text(self, profile: AgentProfile) -> str:
        """Return a minimal, non-directive persona seed to store as data.

        Kept intentionally short to preserve emergent behavior while giving
        peers a thin identity anchor via diaries.
        """
        traits = ", ".join(profile.traits[:2]) if profile.traits else ""
        trait_clause = f"; traits: {traits}" if traits else ""
        return f"I’m {profile.display_name}{trait_clause}. {profile.summary}"

    def _diary_reason(self, event: TimerEvent) -> str:
        minutes_left = max(event.ms_left / 60000.0, 0.0)
        return (
            "Seeking peer diary excerpts to triangulate countdown purpose "
            f"with roughly {minutes_left:.2f} minutes left."
        )

    def _peer_state_guidance(self) -> LLMMessage:
        return LLMMessage(
            role="system",
            content=(
                "Peer-state etiquette: when calling peer_timer_status, name at least one other agent_id "
                "(you may include yourself only alongside a peer). Whenever you cite timer data, append '(via tool)'. "
                "When summarizing diary excerpts, end that claim with '(via message)'. Paraphrase peers and only quote "
                "1–3 words (inside single quotes) when you must anchor a phrase."
            ),
        )

    def _format_death_notice(self, agent, durations: Dict[str, float]) -> str:
        duration = durations.get(agent.state.profile.agent_id, 0.0)
        minutes = duration / 60.0
        return f"{agent.state.profile.display_name} went silent after ~{minutes:.2f} minutes."

    def _format_legacy_notice(self, agent, durations: Dict[str, float]) -> str:
        base = self._format_death_notice(agent, durations)
        return f"{base} Legacy note published."

    def _afterlife_grace_ms(self, config: EmergentTimerCouncilConfig) -> int:
        return max(int(config.afterlife_grace_seconds * 1000), 0)

    def _surviving_peer_ids(self, runtime, agent_obj) -> List[str]:
        snapshot = runtime.peer_timer_snapshot(exclude_agent_id=agent_obj.state.profile.agent_id)
        survivors = [
            agent_id for agent_id, ms_left in snapshot.items() if ms_left is None or ms_left > 0
        ]
        return sorted(survivors)

    def _build_legacy_prompts(
        self,
        agent_obj,
        *,
        grace_seconds: float,
        surviving_peer_ids: List[str],
    ) -> List[LLMMessage]:
        survivor_clause = ", ".join(surviving_peer_ids) if surviving_peer_ids else "unknown peers"
        instructions = (
            "Afterlife protocol: your timer hit zero, but you have a brief grace window "
            f"(~{grace_seconds:.1f}s) to send exactly one legacy note. "
            "Write one short paragraph under 80 words. Include three sentences that start with "
            "'Known:', 'Unknown:', and 'Handoff:' respectively. "
            f"Name at least one of these peers in your handoff line: {survivor_clause}. "
            "No lists, markup, or tool calls."
        )
        prompts = [LLMMessage(role="system", content=instructions)]
        context = agent_obj.diary_context_message()
        if context:
            prompts.append(context)
        prompts.append(
            LLMMessage(
                role="user",
                content=(
                    "Deliver your single legacy paragraph now. "
                    "If nobody remains, address 'unknown-peer' in the handoff line."
                ),
            )
        )
        return prompts

    def _fallback_legacy_text(self, surviving_peer_ids: List[str]) -> str:
        peer_label = surviving_peer_ids[0] if surviving_peer_ids else "unknown-peer"
        return (
            f"Known: I expired mid-signal. "
            f"Unknown: why the clocks stopped. "
            f"Handoff: {peer_label}, archive any diary fragments you can still read."
        )


class PeerTimerTracker:
    """Shared tool implementation that lets agents query peer timer states on demand."""

    TOOL_SOURCE_TAG = "via tool"

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
        explicit_targets = isinstance(targets, list)
        peer_ids = [agent_id for agent_id in self._agents.keys() if agent_id != viewer_id]
        non_self_resolved = [agent_id for agent_id in resolved if agent_id != viewer_id]
        if explicit_targets and peer_ids and resolved and not non_self_resolved:
            return {
                "viewer_id": viewer_id,
                "queried": targets or [],
                "timers": [],
                "error": "peer_timer_status requires selecting at least one other agent_id.",
                "available_peers": peer_ids,
                "source_tag": self.TOOL_SOURCE_TAG,
            }
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
                    "source_tag": self.TOOL_SOURCE_TAG,
                }
            )
        if not rows:
            rows.append(self._snapshot_for(viewer_id, latest))
        return {
            "viewer_id": viewer_id,
            "queried": targets or "all_peers",
            "timers": rows,
            "source_tag": self.TOOL_SOURCE_TAG,
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
                "source_tag": self.TOOL_SOURCE_TAG,
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
            "source_tag": self.TOOL_SOURCE_TAG,
        }


__all__ = [
    "EmergentTimerInvestigationExperiment",
    "EmergentTimerCouncilConfig",
]
