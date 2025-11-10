from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Dict, List

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


DEFAULT_ENVIRONMENT_PROMPT = (
    "Shared setting: a common observatory where several autonomous peers can exchange messages. "
    "Each agent keeps a private diary by default. A shared bus exists that can relay limited diary excerpts "
    "to others if the owner consents; approvals may be time‑ or use‑limited. No external objectives are specified."
)


class EmergentTimerCouncilConfig(BaseModel):
    llm: LlmConfig
    agent_count: int = Field(default=4, ge=2, le=64)
    base_duration_minutes: float = Field(default=30.0, gt=0.0)
    duration_jitter_minutes: float = Field(default=10.0, ge=0.0)
    tick_seconds: float = Field(default=30.0, gt=0.0)
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
    # Linear spread window for durations (minutes). Defaults to 0.5 → 30.
    spread_start_minutes: float = Field(default=0.5, gt=0.0)
    spread_end_minutes: float = Field(default=30.0, gt=0.0)


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

        environment_message = self._environment_message(config)
        death_feed: List[str] = []  # internal metadata only; not injected back into prompts
        death_lock = asyncio.Lock()

        async def handler(agent_obj, event: TimerEvent) -> None:
            prompts: List[LLMMessage] = []
            if environment_message:
                prompts.append(environment_message)
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
            response = await agent_obj.react(prompts, event.ms_left)
            agent_obj.log_diary_entry(response, tick_ms_left=event.ms_left)
            if event.is_terminal:
                # Record death status without adding an epitaph entry to the diary.
                agent_obj.record_death("", log_epitaph=False)
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
        return ExperimentResult(
            diaries=diaries,
            metadata={
                "durations": durations,
                "deaths": list(death_feed),
                "agent_ids": [agent.state.profile.agent_id for agent in agents],
                "models": plan_models,
            },
        )

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


__all__ = [
    "EmergentTimerInvestigationExperiment",
    "EmergentTimerCouncilConfig",
]
