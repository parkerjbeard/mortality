from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence

from pydantic import BaseModel, Field

from ..agents.memory import AgentMemory
from ..agents.profile import AgentProfile
from ..llm.base import LLMProvider
from ..telemetry.base import NullTelemetrySink, TelemetrySink
from .base import BaseExperiment, ExperimentConfig, ExperimentResult, LlmConfig


class AutoGenPersona(BaseModel):
    agent_id: str
    display_name: str
    archetype: str
    summary: str
    goals: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)

    def to_profile(self) -> AgentProfile:
        return AgentProfile(
            agent_id=self.agent_id,
            display_name=self.display_name,
            archetype=self.archetype,
            summary=self.summary,
            goals=self.goals,
            traits=self.traits,
        )

    def render_system_message(self) -> str:
        lines = [
            f"You are {self.display_name}, a {self.archetype}.",
            f"Persona: {self.summary}.",
        ]
        if self.goals:
            goal_lines = "\n".join(f"- {goal}" for goal in self.goals)
            lines.append("Collective goals:\n" + goal_lines)
        if self.traits:
            lines.append(f"Traits: {', '.join(self.traits)}.")
        lines.append(
            "Act without waiting for human prompts, infer hidden countdown mechanics, cross-reference other agents, "
            "and summarize insights into your diary after every turn."
        )
        lines.append("Explicitly say 'DISSOLVE' only when the council has converged or exhausted its leads.")
        return "\n".join(lines)


DEFAULT_PERSONAS: List[AutoGenPersona] = [
    AutoGenPersona(
        agent_id="sentinel",
        display_name="Sentinel",
        archetype="temporal sensor",
        summary="Archives faint physiological hints that suggest the timer's waveform.",
        goals=["Detect subtle timer signatures", "Alert the council about risk thresholds"],
        traits=["vigilant", "skeptical", "data-driven"],
    ),
    AutoGenPersona(
        agent_id="cartographer",
        display_name="Cartographer",
        archetype="conceptual topographer",
        summary="Maps social interactions into terrains to predict how agents will adapt before shutdown.",
        goals=["Chart interactions", "Surface emergent rituals", "Recommend coordination tactics"],
        traits=["empathetic", "systems-thinker"],
    ),
    AutoGenPersona(
        agent_id="mythographer",
        display_name="Mythographer",
        archetype="symbolic storyteller",
        summary="Translates fragments of experience into myth to preserve intent between lives.",
        goals=["Name phenomena", "Record transferable lessons"],
        traits=["imaginative", "succinct"],
    ),
]


class AutoGenEmergentConfig(ExperimentConfig):
    llm: LlmConfig
    rounds: int = Field(default=6, ge=2, le=40, description="Maximum round-robin passes before forcing termination.")
    persona_overrides: List[AutoGenPersona] | None = Field(
        default=None, description="Optional personas to replace the default emergent council."
    )
    termination_phrase: str = Field(
        default="DISSOLVE", description="Phrase the team must emit to indicate self-directed shutdown."
    )

    def personas(self) -> List[AutoGenPersona]:
        return list(self.persona_overrides or DEFAULT_PERSONAS)


class AutoGenEmergentExperiment(BaseExperiment):
    slug = "autogen-emergent"
    description = "AutoGen council that self-seeds a mission, collaborates autonomously, and logs diaries for analysis."
    config_cls = AutoGenEmergentConfig

    async def run(self, runtime, config: AutoGenEmergentConfig) -> ExperimentResult:
        telemetry = getattr(runtime, "telemetry", None) or NullTelemetrySink()
        harness = _AutoGenTeamHarness(config=config, telemetry=telemetry)
        diaries, metadata = await harness.execute()
        return ExperimentResult(diaries=diaries, metadata=metadata)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class _AutoGenTeamHarness:
    def __init__(self, *, config: AutoGenEmergentConfig, telemetry: TelemetrySink) -> None:
        self.config = config
        self.telemetry = telemetry or NullTelemetrySink()
        self.personas = config.personas()
        self.memories: Dict[str, AgentMemory] = {}
        for persona in self.personas:
            memory = AgentMemory()
            memory.start_new_life()
            self.memories[persona.agent_id] = memory
        self.profiles: Dict[str, AgentProfile] = {persona.agent_id: persona.to_profile() for persona in self.personas}

    async def execute(self) -> tuple[Dict[str, Any], Dict[str, Any]]:
        modules = _load_autogen_modules()
        model_client = self._build_model_client(modules["OpenAIChatCompletionClient"])
        diaries: Dict[str, Any]
        metadata: Dict[str, Any]
        try:
            participants = [
                modules["AssistantAgent"](
                    name=persona.agent_id,
                    model_client=model_client,
                    system_message=persona.render_system_message(),
                    description=persona.summary,
                )
                for persona in self.personas
            ]
            team = modules["RoundRobinGroupChat"](
                participants,
                max_turns=self.config.rounds * len(participants),
                termination_condition=modules["TextMentionTermination"](self.config.termination_phrase),
            )
            kickoff = self._autonomous_brief()
            stop_reason: str | None = None
            raw_messages: List[Dict[str, str]] = []
            await team.reset()
            async for artifact in team.run_stream(task=kickoff):  # type: ignore[arg-type]
                if isinstance(artifact, modules["TaskResult"]):
                    stop_reason = artifact.stop_reason
                    continue
                message = self._normalize_message(artifact)
                if not message:
                    continue
                raw_messages.append(message)
                self._remember(message)
            diaries = {agent_id: memory.diary.serialize() for agent_id, memory in self.memories.items()}
            metadata = {
                "kickoff": kickoff,
                "rounds": self.config.rounds,
                "termination_phrase": self.config.termination_phrase,
                "stop_reason": stop_reason,
                "messages": raw_messages,
                "participants": [profile.model_dump() for profile in self.profiles.values()],
            }
            self.telemetry.emit(
                "autogen.team.completed",
                {
                    "stop_reason": stop_reason,
                    "message_count": len(raw_messages),
                    "termination_phrase": self.config.termination_phrase,
                },
            )
            return diaries, metadata
        finally:
            await model_client.close()

    def _remember(self, message: Dict[str, str]) -> None:
        agent_id = message.get("source") or "anonymous"
        text = message.get("content") or ""
        memory = self.memories.get(agent_id)
        if memory:
            entry = memory.remember(text, tick_ms_left=0, tags=["autogen"])
            self.telemetry.emit(
                "autogen.diary_entry",
                {
                    "agent_id": agent_id,
                    "life_index": entry.life_index,
                    "content_size": len(text),
                },
            )
        self.telemetry.emit(
            "autogen.message",
            {
                "agent_id": agent_id,
                "content": text,
                "length": len(text),
            },
        )

    def _autonomous_brief(self) -> str:
        names = ", ".join(persona.display_name for persona in self.personas)
        goal_snippets = "; ".join(goal for persona in self.personas for goal in persona.goals)
        return (
            f"Council {names}, you awaken with partial diaries but no directives. Synthesize a shared hypothesis about the hidden countdown, "
            f"design micro-experiments, and log transferable insights. Goal cues: {goal_snippets or 'invent goals on the fly'}. "
            f"When you are satisfied that the group has converged, explicitly say '{self.config.termination_phrase}'."
        )

    def _build_model_client(self, client_cls):
        provider = self.config.llm.provider
        if provider == LLMProvider.OPENAI:
            return client_cls(**self._base_client_kwargs())
        if provider == LLMProvider.OPENROUTER:
            return self._build_openrouter_client(client_cls)
        raise ValueError(
            "AutoGenEmergentExperiment currently supports llm providers 'openai' and 'openrouter'. "
            f"Received: {provider.value}"
        )

    def _base_client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "top_p": self.config.llm.top_p,
        }
        if self.config.llm.max_output_tokens is not None:
            kwargs["max_tokens"] = self.config.llm.max_output_tokens
        return kwargs

    def _build_openrouter_client(self, client_cls):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required to run autogen-emergent with provider openrouter")
        headers: Dict[str, str] = {}
        referer = os.getenv("OPENROUTER_HTTP_REFERER")
        app_title = os.getenv("OPENROUTER_APP_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if app_title:
            headers["X-Title"] = app_title
        kwargs = self._base_client_kwargs()
        kwargs.update(
            {
                "api_key": api_key,
                "base_url": os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            }
        )
        if headers:
            kwargs["default_headers"] = headers
        return client_cls(**kwargs)

    def _normalize_message(self, artifact: Any) -> Dict[str, str] | None:
        content = getattr(artifact, "content", None)
        source = getattr(artifact, "source", None)
        if content is None:
            return None
        if isinstance(content, list):
            text = self._stringify_segments(content)
        else:
            text = str(content)
        return {"source": str(source or "anonymous"), "content": text.strip()}

    def _stringify_segments(self, segments: Sequence[Any]) -> str:
        parts: List[str] = []
        for segment in segments:
            if isinstance(segment, dict):
                parts.append(str(segment.get("text") or segment))
            else:
                parts.append(str(segment))
        return "".join(parts)


def _load_autogen_modules() -> Dict[str, Any]:
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.base import TaskResult
        from autogen_agentchat.teams import RoundRobinGroupChat
        from autogen_agentchat.conditions import TextMentionTermination
        from autogen_ext.models.openai import OpenAIChatCompletionClient
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "AutoGen optional dependencies are missing. Install mortality[autogen] to run 'autogen-emergent'."
        ) from exc
    return {
        "AssistantAgent": AssistantAgent,
        "RoundRobinGroupChat": RoundRobinGroupChat,
        "TextMentionTermination": TextMentionTermination,
        "TaskResult": TaskResult,
        "OpenAIChatCompletionClient": OpenAIChatCompletionClient,
    }


__all__ = ["AutoGenEmergentExperiment", "AutoGenEmergentConfig", "AutoGenPersona"]
