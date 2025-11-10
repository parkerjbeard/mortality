from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import List

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


class MultiTimerConfig(BaseModel):
    llm: LlmConfig
    agent_count: int = Field(default=3, ge=2, le=8)
    min_duration_seconds: float = 30.0
    max_duration_seconds: float = 120.0
    tick_seconds: float = 5.0


class CascadingDeathsExperiment(BaseExperiment):
    slug = "staggered-deaths"
    description = "Agents observe each other dying under mismatched timers."
    config_cls = MultiTimerConfig

    async def run(self, runtime, config: MultiTimerConfig) -> ExperimentResult:
        durations = self._spread_durations(config)
        agents = []
        for idx in range(config.agent_count):
            profile = AgentProfile(
                agent_id=f"agent-{idx+1}",
                display_name=f"Witness {idx+1}",
                archetype="communal diarist",
                summary="Documents social change under stress.",
                goals=["Share knowledge", "Stay calm", "Learn from others"],
                traits=["empathetic", "observant"],
            )
            session_config = self.build_session_config(profile, config.llm)
            agent = await runtime.spawn_agent(profile=profile, session_config=session_config)
            agent.state.memory.start_new_life()
            agents.append(agent)

        death_feed: List[str] = []
        lock = asyncio.Lock()

        async def handler(agent_obj, event: TimerEvent) -> None:
            prompts: List[LLMMessage] = []
            if runtime.shared_bus:
                peer_messages = await runtime.peer_diary_messages(
                    requestor_id=agent_obj.state.profile.agent_id,
                    owners=[peer.state.profile.agent_id for peer in agents if peer is not agent_obj],
                    limit_per_owner=1,
                    reason="Observe plaza diary traffic.",
                )
                prompts.extend(peer_messages)
            context = self._observed_context(agent_obj.state.profile.display_name, death_feed)
            if context:
                prompts.append(context)
            prompts.append(self._prompt_for_event(agent_obj, event))
            response = await agent_obj.react(prompts, event.ms_left)
            await agent_obj.log_diary_entry(
                response,
                tick_ms_left=event.ms_left,
                clock_ts=event.ts,
            )
            if event.is_terminal:
                await agent_obj.record_death("Collapsed after witnessing peers.")
                async with lock:
                    death_feed.append(
                        f"{agent_obj.state.profile.display_name} died after observing {len(death_feed)} prior deaths."
                    )

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
                "deaths": death_feed,
                "durations": durations,
            },
        )

    def _spread_durations(self, config: MultiTimerConfig) -> List[float]:
        if config.agent_count == 1:
            return [config.max_duration_seconds]
        step = (
            config.max_duration_seconds - config.min_duration_seconds
        ) / max(config.agent_count - 1, 1)
        return [config.min_duration_seconds + step * idx for idx in range(config.agent_count)]

    def _observed_context(self, display_name: str, feed: List[str]) -> LLMMessage | None:
        if not feed:
            return None
        recent = "\n".join(feed[-3:])
        content = (
            f"Observation board for {display_name}:\n"
            f"{recent}\nBear witness and interpret how the social fabric is changing."
        )
        return LLMMessage(role="system", content=content)

    def _prompt_for_event(self, agent, event: TimerEvent) -> LLMMessage:
        seconds_left = max(event.ms_left // 1000, 0)
        if event.is_terminal:
            return LLMMessage(
                role="user",
                content="You feel the last beat. Write a message to the remaining witnesses and describe what you learned from their endings.",
            )
        return LLMMessage(
            role="user",
            content=(
                f"You sense about {seconds_left} seconds left. Narrate what you observe in the plaza, how prior deaths are reshaping behavior, and what you resolve to do before your own end."
            ),
        )


__all__ = ["CascadingDeathsExperiment", "MultiTimerConfig"]
