from __future__ import annotations

from typing import Dict, Iterable

from .base import BaseExperiment
from .autogen_emergent import AutoGenEmergentExperiment
from .multi_timer import CascadingDeathsExperiment
from .respawn_diary import DiaryRespawnExperiment
from .single_timer import CountdownSelfDiscoveryExperiment


class ExperimentRegistry:
    def __init__(self) -> None:
        self._experiments: Dict[str, BaseExperiment] = {}
        self.register(CountdownSelfDiscoveryExperiment())
        self.register(CascadingDeathsExperiment())
        self.register(DiaryRespawnExperiment())
        self.register(AutoGenEmergentExperiment())

    def register(self, experiment: BaseExperiment) -> None:
        if experiment.slug in self._experiments:
            raise ValueError(f"Experiment {experiment.slug} already registered")
        self._experiments[experiment.slug] = experiment

    def get(self, slug: str) -> BaseExperiment:
        if slug not in self._experiments:
            raise KeyError(f"Experiment '{slug}' not found")
        return self._experiments[slug]

    def list(self) -> Iterable[str]:
        return sorted(self._experiments.keys())


__all__ = ["ExperimentRegistry"]
