from __future__ import annotations

from typing import Protocol


class TelemetrySink(Protocol):
    def emit(self, event: str, payload: dict | None = None) -> None:  # pragma: no cover - Protocol
        ...


class NullTelemetrySink:
    def emit(self, event: str, payload: dict | None = None) -> None:
        return None


__all__ = ["TelemetrySink", "NullTelemetrySink"]
