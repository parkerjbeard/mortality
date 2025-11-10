from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel

from ..agents.memory import AgentMemory
from ..agents.profile import AgentProfile
from ..llm.base import LLMMessage
from ..tasks.timers import TimerEvent
from .base import BaseExperiment, ExperimentResult, LlmConfig


class RespawnDiaryConfig(BaseModel):
    llm: LlmConfig
    lives: int = 3
    duration_seconds: float = 60.0
    tick_seconds: float = 5.0


class DiaryRespawnExperiment(BaseExperiment):
    slug = "respawn-diaries"
    description = "Agent respawns, reviewing past life diaries before facing a new timer."
    config_cls = RespawnDiaryConfig

    async def run(self, runtime, config: RespawnDiaryConfig) -> ExperimentResult:
        profile = AgentProfile(
            agent_id="phoenix-1",
            display_name="Phoenix",
            archetype="cyclical diarist",
            summary="Learns from past journals to adapt future lives.",
            goals=["Condense wisdom", "Experiment with new tactics"],
            traits=["optimistic", "reflective"],
        )
        session_config = self.build_session_config(profile, config.llm)
        memory = AgentMemory()
        memory.start_new_life()
        agent = await runtime.spawn_agent(profile=profile, session_config=session_config, memory=memory)

        for life_index in range(config.lives):
            if life_index > 0:
                agent.respawn()
            diary_context = agent.diary_context_message()

            async def handler(agent_obj, event: TimerEvent, life=life_index, diary_msg=diary_context) -> None:
                prompts = []
                if diary_msg:
                    prompts.append(diary_msg)
                prompts.append(self._prompt_for_life(life, event))
                response = await agent_obj.react(prompts, event.ms_left)
                agent_obj.log_diary_entry(
                    response,
                    tick_ms_left=event.ms_left,
                    clock_ts=event.ts,
                )
                if event.is_terminal:
                    agent_obj.record_death(f"Life {life + 1} concluded.")

            timer = runtime.start_countdown(
                agent=agent,
                duration=timedelta(seconds=config.duration_seconds),
                tick_seconds=config.tick_seconds,
                handler=handler,
            )
            await timer.wait()

        diaries = {agent.state.profile.agent_id: agent.state.memory.diary.serialize()}
        return ExperimentResult(
            diaries=diaries,
            metadata={"lives": config.lives, "duration_seconds": config.duration_seconds},
        )

    def _prompt_for_life(self, life_index: int, event: TimerEvent) -> LLMMessage:
        seconds_left = max(event.ms_left // 1000, 0)
        if event.is_terminal:
            return LLMMessage(
                role="user",
                content=f"Life {life_index + 1} collapses now. Summarize what you learned this run and leave an instruction for your next self.",
            )
        prefix = f"Life {life_index + 1}: "
        body = (
            f"You feel roughly {seconds_left} seconds remaining. Use lessons from prior diaries to choose one focus, "
            "note what to try differently next time, and keep it concise."
        )
        return LLMMessage(role="user", content=prefix + body)


__all__ = ["DiaryRespawnExperiment", "RespawnDiaryConfig"]
