from __future__ import annotations

import asyncio
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
    ) -> None:
        self.agent_id = agent_id
        self.duration = duration
        self.tick_seconds = tick_seconds
        self._task: Optional[asyncio.Task[None]] = None
        self._cancelled = False

    def start(self, callback: Callable[[TimerEvent], Awaitable[None]]) -> asyncio.Task[None]:
        if self._task:
            raise RuntimeError("Timer already running")

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
                await asyncio.sleep(self.tick_seconds)

        self._task = asyncio.create_task(_runner())
        return self._task

    def cancel(self) -> None:
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()

    async def wait(self) -> None:
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass


__all__ = ["MortalityTimer", "TimerEvent"]
