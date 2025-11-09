from __future__ import annotations

import json
from typing import Iterable, Protocol


class TelemetrySink(Protocol):
    def emit(self, event: str, payload: dict | None = None) -> None:  # pragma: no cover - Protocol
        ...


class NullTelemetrySink:
    def emit(self, event: str, payload: dict | None = None) -> None:
        return None


class ConsoleTelemetrySink:
    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty

    def emit(self, event: str, payload: dict | None = None) -> None:
        if not payload:
            print(f"[telemetry] {event}")
            return
        if self.pretty:
            body = json.dumps(payload, indent=2, ensure_ascii=False)
        else:
            body = json.dumps(payload, ensure_ascii=False)
        print(f"[telemetry] {event}: {body}")


class FanoutTelemetrySink:
    def __init__(self, sinks: Iterable[TelemetrySink]) -> None:
        self.sinks = list(sinks)

    def emit(self, event: str, payload: dict | None = None) -> None:
        for sink in self.sinks:
            sink.emit(event, payload)


__all__ = ["TelemetrySink", "NullTelemetrySink", "ConsoleTelemetrySink", "FanoutTelemetrySink"]
