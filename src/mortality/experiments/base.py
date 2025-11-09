from __future__ import annotations

import abc
from typing import Any, Dict, Type

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile
from ..llm.base import LLMProvider, LLMSessionConfig

class LlmConfig(BaseModel):
    provider: LLMProvider
    model: str
    temperature: float = 0.7
    top_p: float = 0.9
    max_output_tokens: int | None = 512


class ExperimentResult(BaseModel):
    diaries: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    llm: LlmConfig


class BaseExperiment(abc.ABC):
    slug: str
    description: str
    config_cls: Type[ExperimentConfig] = ExperimentConfig

    def parse_config(self, **values: Any) -> ExperimentConfig:
        return self.config_cls(**values)

    @abc.abstractmethod
    async def run(self, runtime, config: ExperimentConfig) -> ExperimentResult:  # pragma: no cover - interface
        ...

    def build_session_config(self, profile: AgentProfile, llm_config: LlmConfig) -> LLMSessionConfig:
        return LLMSessionConfig(
            provider=llm_config.provider,
            model=llm_config.model,
            system_prompt=profile.render_system_prompt(),
            temperature=llm_config.temperature,
            top_p=llm_config.top_p,
            max_output_tokens=llm_config.max_output_tokens,
        )


__all__ = ["BaseExperiment", "ExperimentConfig", "ExperimentResult", "LlmConfig"]
