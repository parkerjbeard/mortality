from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from pydantic import BaseModel, Field


class DiaryEntry(BaseModel):
    life_index: int
    tick_ms_left: int
    text: str
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Diary(BaseModel):
    entries: List[DiaryEntry] = Field(default_factory=list)

    def add(self, entry: DiaryEntry) -> None:
        self.entries.append(entry)

    def latest(self) -> Optional[DiaryEntry]:
        return self.entries[-1] if self.entries else None

    def serialize(self) -> List[dict]:
        return [entry.model_dump(mode="json") for entry in self.entries]

    @classmethod
    def from_iterable(cls, entries: Iterable[DiaryEntry]) -> "Diary":
        return cls(entries=list(entries))


class AgentMemory(BaseModel):
    """Lifecycle-aware memory capsule."""

    diary: Diary = Field(default_factory=Diary)
    life_index: int = 0

    def start_new_life(self) -> None:
        self.life_index += 1

    def remember(self, text: str, tick_ms_left: int, tags: Optional[List[str]] = None) -> DiaryEntry:
        entry = DiaryEntry(
            life_index=self.life_index,
            tick_ms_left=tick_ms_left,
            text=text,
            tags=tags or [],
        )
        self.diary.add(entry)
        return entry
__all__ = ["Diary", "DiaryEntry", "AgentMemory"]
