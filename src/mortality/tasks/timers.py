from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Awaitable, Callable, Optional


@dataclass
class TimerEvent:
    agent_id: str
    ms_left: int
    tick_index: int
    is_terminal: bool
    ts: datetime


class MortalityTimer:
    """Async countdown that emits ticks until death."""

    def __init__(
        self,
        agent_id: str,
        duration: timedelta,
        tick_seconds: float = 1.0,
        *,
        tick_seconds_max: float | None = None,
        tick_jitter_ms: float = 0.0,
    ) -> None:
        self.agent_id = agent_id
        self.duration = duration
        if tick_seconds <= 0:
            raise ValueError("tick_seconds must be positive")
        if tick_seconds_max is not None and tick_seconds_max < tick_seconds:
            raise ValueError("tick_seconds_max must be >= tick_seconds")
        self.tick_seconds = tick_seconds
        self.tick_seconds_max = tick_seconds_max
        self.tick_jitter_ms = max(tick_jitter_ms, 0.0)
        self._task: Optional[asyncio.Task[None]] = None
        self._cancelled = False
        self._nudge_event: Optional[asyncio.Event] = None

    def start(self, callback: Callable[[TimerEvent], Awaitable[None]]) -> asyncio.Task[None]:
        if self._task:
            raise RuntimeError("Timer already running")

        self._nudge_event = asyncio.Event()

        async def _runner() -> None:
            start_ts = monotonic()
            tick_index = 0
            while True:
                elapsed = monotonic() - start_ts
                remaining = max(self.duration.total_seconds() - elapsed, 0.0)
                ms_left = int(remaining * 1000)
                is_terminal = remaining <= 0.0
                event = TimerEvent(
                    agent_id=self.agent_id,
                    ms_left=ms_left,
                    tick_index=tick_index,
                    is_terminal=is_terminal,
                    ts=datetime.now(timezone.utc),
                )
                await callback(event)
                if is_terminal or self._cancelled:
                    break
                tick_index += 1
                await self._await_next_tick()

        self._task = asyncio.create_task(_runner())
        return self._task

    def cancel(self) -> None:
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
        if self._nudge_event:
            self._nudge_event.set()

    async def wait(self) -> None:
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def request_micro_turn(self) -> None:
        """Force the next tick to run without waiting the full interval."""

        if self._task is None or self._task.done() or self._cancelled:
            return
        if not self._nudge_event:
            return
        self._nudge_event.set()

    def _next_interval_seconds(self) -> float:
        upper = self.tick_seconds_max if self.tick_seconds_max is not None else self.tick_seconds
        base = random.uniform(self.tick_seconds, upper) if upper > self.tick_seconds else self.tick_seconds
        if self.tick_jitter_ms:
            jitter = random.uniform(-self.tick_jitter_ms, self.tick_jitter_ms) / 1000.0
            base += jitter
        return max(base, 0.05)

    async def _await_next_tick(self) -> None:
        delay = self._next_interval_seconds()
        if delay <= 0:
            return
        event = self._nudge_event
        if not event:
            await asyncio.sleep(delay)
            return
        if event.is_set():
            event.clear()
            return
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        else:
            event.clear()


__all__ = ["MortalityTimer", "TimerEvent"]
