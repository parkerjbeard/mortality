from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from typing import Optional, Set, Tuple

_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
_TIMER_TOKENS = {
    "timer",
    "countdown",
    "clock",
    "tick",
    "ticks",
    "ticking",
    "seconds",
    "second",
    "ms",
    "millisecond",
    "milliseconds",
    "remaining",
    "left",
    "time",
    "delta",
    "status",
    "msleft",
    "ms_left",
}
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "but",
    "for",
    "nor",
    "or",
    "so",
    "yet",
    "into",
    "onto",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "about",
    "after",
    "before",
    "over",
    "under",
    "again",
    "still",
    "very",
    "more",
    "less",
    "than",
    "then",
    "when",
    "while",
    "just",
    "only",
    "also",
    "like",
}
DEFAULT_INTERVAL_MS = 1500


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: Optional[str] = None
    new_keywords: Set[str] | None = None


class ActionGate:
    """Applies jittered dwell + duplicate/timer-only suppression before actions."""

    def __init__(
        self,
        *,
        reflect_range: Tuple[float, float] = (0.65, 0.95),
        act_range: Tuple[float, float] = (0.55, 0.85),
        min_dwell_seconds: float = 0.2,
        max_dwell_seconds: float = 0.75,
        fallback_interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        self._reflect_range = reflect_range
        self._act_range = act_range
        self._min_dwell = min_dwell_seconds
        self._max_dwell = max_dwell_seconds
        self._tick_interval_ms = fallback_interval_ms
        self._last_action_signature: Tuple[str, str] | None = None
        self._last_diary_keywords: Set[str] = set()

    def note_interval(self, interval_ms: Optional[int]) -> None:
        if interval_ms and interval_ms > 0:
            self._tick_interval_ms = interval_ms

    def reset(self) -> None:
        """Clear any cached signatures/keywords so the next life starts fresh."""
        self._last_action_signature = None
        self._last_diary_keywords.clear()

    async def guard_assistant(self, *, text: str) -> GateDecision:
        await self._dwell(stage="reflect")
        normalized = self._normalize(text)
        if not normalized:
            return GateDecision(False, "empty assistant output")
        if self._is_timer_only(normalized):
            return GateDecision(False, "timer-only status")
        if self._is_repeat("assistant", normalized):
            return GateDecision(False, "assistant repeat")
        self._last_action_signature = ("assistant", normalized)
        return GateDecision(True)

    async def guard_diary(self, *, text: str) -> GateDecision:
        await self._dwell(stage="act")
        normalized = self._normalize(text)
        if not normalized:
            return GateDecision(False, "empty diary entry")
        if self._is_repeat("diary", normalized):
            return GateDecision(False, "diary repeat")
        keywords = self._keyword_set(text)
        if not keywords:
            return GateDecision(False, "no facts/beliefs extracted")
        new_items = keywords - self._last_diary_keywords
        if not new_items:
            return GateDecision(False, "no diary delta")
        self._last_action_signature = ("diary", normalized)
        self._last_diary_keywords = keywords
        return GateDecision(True, new_keywords=new_items)

    async def _dwell(self, *, stage: str) -> None:
        interval_seconds = self._tick_interval_ms / 1000.0
        capped_interval = min(interval_seconds, self._max_dwell)
        base_seconds = max(capped_interval, self._min_dwell)
        jitter_range = self._reflect_range if stage == "reflect" else self._act_range
        dwell_seconds = max(base_seconds * random.uniform(*jitter_range), self._min_dwell)
        await asyncio.sleep(dwell_seconds)

    def _normalize(self, text: str) -> str:
        collapsed = " ".join(text.strip().split())
        return collapsed.lower()

    def _is_repeat(self, kind: str, normalized: str) -> bool:
        return self._last_action_signature == (kind, normalized)

    def _is_timer_only(self, normalized: str) -> bool:
        tokens = _TOKEN_PATTERN.findall(normalized)
        if not tokens:
            return True
        for token in tokens:
            if token.isdigit():
                continue
            if token not in _TIMER_TOKENS:
                return False
        return True

    def _keyword_set(self, text: str) -> Set[str]:
        tokens = _TOKEN_PATTERN.findall(text.lower())
        keywords = {
            token
            for token in tokens
            if len(token) > 3 and token not in _STOPWORDS and token not in _TIMER_TOKENS
        }
        return keywords

__all__ = ["ActionGate", "GateDecision"]
