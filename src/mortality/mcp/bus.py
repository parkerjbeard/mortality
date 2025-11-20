from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Sequence

from pydantic import BaseModel, Field

from ..agents.profile import AgentProfile


class BroadcastScope(BaseModel):
    """Filters that describe which broadcast snippets a requester wants."""

    limit: int = Field(default=3, ge=1)

    def describe(self) -> str:
        return f"limit={self.limit}"


class BroadcastResource(BaseModel):
    owner_id: str
    owner_display_name: str
    uri: str
    text: str
    mime_type: str = "text/plain"
    entries: List[Dict[str, Any]] = Field(default_factory=list)
    annotations: Dict[str, Any] = Field(default_factory=dict)

    def to_message(self):
        from ..llm.base import LLMMessage

        return LLMMessage(role="system", content=self.text)


class BroadcastSnippet(BaseModel):
    """A short outward-facing snippet intended for the shared bus."""

    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SharedMCPBus:
    """Central bus that exposes only explicit broadcast snippets (not private diaries)."""

    def __init__(self) -> None:
        self._broadcasts: Dict[str, List[BroadcastSnippet]] = {}
        self._profiles: Dict[str, AgentProfile] = {}
        self._listeners: List[Callable[[str], None]] = []
        self._active_turn_agent: str | None = None
        self._active_turn_index: int | None = None

    def register_agent(self, profile: AgentProfile) -> None:
        self._profiles[profile.agent_id] = profile
        self._broadcasts.setdefault(profile.agent_id, [])

    def publish_broadcast(self, agent_id: str, text: str) -> None:
        if self._active_turn_agent and agent_id != self._active_turn_agent:
            return
        bucket = self._broadcasts.setdefault(agent_id, [])
        bucket.append(BroadcastSnippet(text=text))
        for listener in list(self._listeners):
            try:
                listener(agent_id)
            except Exception:
                continue

    def subscribe_broadcasts(self, callback: Callable[[str], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def start_turn(self, agent_id: str, turn_index: int) -> None:
        self._active_turn_agent = agent_id
        self._active_turn_index = turn_index

    def end_turn(self, agent_id: str) -> None:
        if self._active_turn_agent == agent_id:
            self._active_turn_agent = None
            self._active_turn_index = None

    async def fetch_broadcasts(
        self,
        *,
        requestor_id: str,
        owners: Sequence[str] | None = None,
        scope: BroadcastScope | None = None,
        reason: str = "",  # reason is unused but preserved for compatibility
    ) -> List[BroadcastResource]:
        scope = scope or BroadcastScope()
        if owners is None:
            owners = [agent_id for agent_id in self._profiles.keys() if agent_id != requestor_id]
        else:
            owners = list(owners)

        resources: List[BroadcastResource] = []
        for owner_id in owners:
            if owner_id == requestor_id:
                continue
            entries = self._filter_broadcasts(owner_id, scope)
            if not entries:
                continue
            resource = self._build_broadcast_resource(owner_id, entries, scope)
            resources.append(resource)
        return resources

    def _filter_broadcasts(self, owner_id: str, scope: BroadcastScope) -> List[BroadcastSnippet]:
        snippets = list(reversed(self._broadcasts.get(owner_id, [])))
        return list(reversed(snippets[: scope.limit]))

    def _build_broadcast_resource(
        self,
        owner_id: str,
        entries: Iterable[BroadcastSnippet],
        scope: BroadcastScope,
    ) -> BroadcastResource:
        profile = self._profiles.get(owner_id)
        owner_name = profile.display_name if profile else owner_id
        lines = [
            f"Broadcasts from {owner_name} ({owner_id}) on the shared bus.",
            f"Scope: {scope.describe()} | cite as 'via bus'",
        ]
        for entry in entries:
            timestamp = entry.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            lines.append(f"- (via bus) at {timestamp}: {entry.text}")
        text = "\n".join(lines)
        return BroadcastResource(
            owner_id=owner_id,
            owner_display_name=owner_name,
            uri=f"mcp+broadcast://{owner_id}/public",
            text=text,
            entries=[entry.model_dump(mode="json") for entry in entries],
            annotations={
                "scope": scope.model_dump(mode="json"),
                "visibility": "public",
            },
        )


__all__ = [
    "BroadcastResource",
    "BroadcastScope",
    "SharedMCPBus",
]
