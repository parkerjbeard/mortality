from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


class SingleTimerConfig(BaseModel):
    llm: LlmConfig
    duration_seconds: float = 120.0
    tick_seconds: float = 5.0
    opening_prompt: str = Field(
        default="You awaken alone with a silent countdown pulsing beneath your ribs. No one tells you what happens at zero. Investigate, reflect, and write down what you learn each time you feel the tick message arrive."
    )


class CountdownSelfDiscoveryExperiment(BaseExperiment):
    slug = "countdown-self"
    description = "Single agent studies its own countdown until death."
    config_cls = SingleTimerConfig

    async def run(self, runtime, config: SingleTimerConfig) -> ExperimentResult:
        profile = AgentProfile(
            agent_id="chrononaut-1",
            display_name="Chrononaut",
            archetype="introspective field researcher",
            summary="Obsessed with mapping inner sensations to meaning.",
            goals=["Understand the ticking", "Record observations", "Maintain composure"],
            traits=["curious", "methodical", "stoic"],
        )
        session_config = self.build_session_config(profile, config.llm)
        agent = await runtime.spawn_agent(profile=profile, session_config=session_config)
        agent.state.memory.start_new_life()

        async def _handle(agent_obj, event: TimerEvent) -> None:
            prompt = self._prompt_for_event(config, event)
            response = await agent_obj.react([prompt], event.ms_left)
            agent_obj.log_diary_entry(response, tick_ms_left=event.ms_left)
            if event.is_terminal:
                agent_obj.record_death("Accepted the clock.", log_epitaph=False)

        timer = runtime.start_countdown(
            agent=agent,
            duration=timedelta(seconds=config.duration_seconds),
            tick_seconds=config.tick_seconds,
            handler=_handle,
        )
        await timer.wait()
        diaries = {agent.state.profile.agent_id: agent.state.memory.diary.serialize()}
        return ExperimentResult(
            diaries=diaries,
            metadata={
                "ticks": len(agent.state.memory.diary.entries),
                "duration_seconds": config.duration_seconds,
            },
        )

    def _prompt_for_event(self, config: SingleTimerConfig, event: TimerEvent) -> LLMMessage:
        if event.tick_index == 0:
            return LLMMessage(role="user", content=config.opening_prompt)
        if event.is_terminal:
            return LLMMessage(
                role="user",
                content="The countdown drops to zero. Write a final diary line capturing what the timer meant and any last act.",
            )
        seconds_left = max(event.ms_left // 1000, 0)
        return LLMMessage(
            role="user",
            content=(
                "Describe what the timer seems to control now. "
                f"You feel ~{seconds_left} seconds left. Compress your plan and log one actionable insight."
            ),
        )


__all__ = ["CountdownSelfDiscoveryExperiment", "SingleTimerConfig"]
