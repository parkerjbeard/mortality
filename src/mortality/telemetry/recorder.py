from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from .base import TelemetrySink


@dataclass
class TelemetryEvent:
    seq: int
    event: str
    ts: str
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StructuredTelemetrySink(TelemetrySink):
    """Collects telemetry events for later export to Mortality UI bundles."""

    def __init__(self) -> None:
        self._events: List[TelemetryEvent] = []
        self._agent_profiles: MutableMapping[str, Dict[str, Any]] = {}

    def emit(self, event: str, payload: dict | None = None) -> None:
        data = payload or {}
        seq = len(self._events)
        ts = datetime.now(timezone.utc).isoformat()
        self._events.append(TelemetryEvent(seq=seq, event=event, ts=ts, payload=data))
        if event == "agent.spawned":
            profile = data.get("profile")
            if isinstance(profile, Mapping):
                agent_id = profile.get("agent_id")
                if isinstance(agent_id, str):
                    self._agent_profiles[agent_id] = dict(profile)

    @property
    def events(self) -> Iterable[TelemetryEvent]:
        return tuple(self._events)

    @property
    def agent_profiles(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._agent_profiles)

    def build_bundle(
        self,
        *,
        diaries: Dict[str, Any],
        metadata: Dict[str, Any],
        experiment: Dict[str, Any],
        config: Dict[str, Any],
        llm: Dict[str, Any],
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return {
            "bundle_type": "mortality/ui#events",
            "schema_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "experiment": experiment,
            "config": config,
            "llm": llm,
            "agents": self.agent_profiles,
            "metadata": metadata,
            "diaries": diaries,
            "events": [event.as_dict() for event in self._events],
            "extra": extra or {},
        }


__all__ = ["StructuredTelemetrySink", "TelemetryEvent"]
