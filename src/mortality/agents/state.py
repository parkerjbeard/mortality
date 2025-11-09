from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..llm.base import LLMSession
from .memory import AgentMemory
from .profile import AgentProfile


class LifecycleStatus(str, Enum):
    ALIVE = "alive"
    EXPIRED = "expired"
    RESPAWNING = "respawning"


@dataclass
class AgentState:
    profile: AgentProfile
    memory: AgentMemory
    session: LLMSession
    status: LifecycleStatus = LifecycleStatus.ALIVE
    last_tick_ms: Optional[int] = None
    visible: bool = True
    metadata: dict = field(default_factory=dict)

    def mark_dead(self) -> None:
        self.status = LifecycleStatus.EXPIRED
        self.visible = False

    def respawn(self) -> None:
        # Respawn completes synchronously, so agents should immediately report as alive again.
        self.status = LifecycleStatus.ALIVE
        self.visible = True


__all__ = ["LifecycleStatus", "AgentState"]
