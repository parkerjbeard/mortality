from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from ..agents.memory import Diary, DiaryEntry
from ..agents.profile import AgentProfile


class DiaryScope(BaseModel):
    """Filters that describe which diary slices a requester wants."""

    limit: int = Field(default=3, ge=1)
    tags: List[str] | None = None
    life_indexes: List[int] | None = None

    def describe(self) -> str:
        pieces: list[str] = []
        if self.tags:
            pieces.append(f"tags={','.join(self.tags)}")
        if self.life_indexes:
            pieces.append(f"life_indexes={','.join(str(i) for i in self.life_indexes)}")
        pieces.append(f"limit={self.limit}")
        return ", ".join(pieces)


class DiaryAccessRequest(BaseModel):
    requestor_id: str
    owner_id: str
    reason: str = ""
    scope: DiaryScope
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiaryAccessDecision(BaseModel):
    approved: bool
    rationale: str = ""
    # Tri-state expiry semantics:
    # - None => use bus default TTL
    # - 0    => no time window; rely on max_uses for validity
    # - >0   => explicit TTL honored exactly
    expires_in_seconds: int | None = None
    # Optional max_uses for stateful consumption; None => unlimited uses
    max_uses: int | None = None


class DiaryAccessToken(BaseModel):
    token: str
    request: DiaryAccessRequest
    scope: DiaryScope
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # None means no time expiry (valid as long as uses remain)
    expires_at: Optional[datetime]
    # Stateful use counting (None => unlimited)
    max_uses: Optional[int] = None
    uses_remaining: Optional[int] = None

    def is_valid(self) -> bool:
        if self.expires_at is not None and datetime.now(timezone.utc) >= self.expires_at:
            return False
        if self.uses_remaining is not None and self.uses_remaining <= 0:
            return False
        return True


class DiaryResource(BaseModel):
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


class DiaryPermissionHandler(Protocol):
    async def approve(self, request: DiaryAccessRequest) -> DiaryAccessDecision:  # pragma: no cover - protocol
        ...


class DiaryPermissionError(RuntimeError):
    pass


class SharedMCPBus:
    """Central bus that exposes diaries as MCP-style resources."""

    def __init__(self, *, token_ttl: timedelta | None = None) -> None:
        self._token_ttl = token_ttl or timedelta(minutes=5)
        self._diaries: Dict[str, Diary] = {}
        self._profiles: Dict[str, AgentProfile] = {}
        self._handlers: Dict[str, DiaryPermissionHandler] = {}
        self._tokens: Dict[str, DiaryAccessToken] = {}
        self._active_grants: Dict[Tuple[str, str], str] = {}
        self._lock = asyncio.Lock()
        # Owner-level toggle to block new grants instantly
        self._paused_owners: set[str] = set()

    def register_agent(
        self,
        profile: AgentProfile,
        handler: DiaryPermissionHandler | None = None,
    ) -> None:
        self._profiles[profile.agent_id] = profile
        self._diaries.setdefault(profile.agent_id, Diary())
        if handler:
            self._handlers[profile.agent_id] = handler

    def publish_entry(self, agent_id: str, entry: DiaryEntry) -> None:
        if agent_id not in self._diaries:
            self._diaries[agent_id] = Diary()
        self._diaries[agent_id].add(entry.model_copy(deep=True))

    def pause_owner(self, owner_id: str, paused: bool = True) -> None:
        """Temporarily block minting new grants for an owner.

        Existing grants continue until expiry/uses are exhausted.
        """
        if paused:
            self._paused_owners.add(owner_id)
        else:
            self._paused_owners.discard(owner_id)

    def revoke_all(self, owner_id: str) -> None:
        """Hard-revoke: invalidate all active grants to this owner."""
        to_remove: list[Tuple[str, str]] = []
        for key, token_id in list(self._active_grants.items()):
            req_id, own_id = key
            if own_id == owner_id:
                to_remove.append(key)
                token = self._tokens.get(token_id)
                if token:
                    token.uses_remaining = 0
                    token.expires_at = datetime.now(timezone.utc)
        for key in to_remove:
            self._active_grants.pop(key, None)
        for token_id, token in list(self._tokens.items()):
            if token.request.owner_id == owner_id:
                self._tokens.pop(token_id, None)

    async def fetch_resources(
        self,
        requestor_id: str,
        owners: Sequence[str] | None = None,
        scope: DiaryScope | None = None,
        reason: str = "",
    ) -> List[DiaryResource]:
        scope = scope or DiaryScope()
        await self._prune_tokens()
        if owners is None:
            owners = [
                agent_id for agent_id in self._profiles.keys() if agent_id != requestor_id
            ]
        else:
            owners = list(owners)
        resources: List[DiaryResource] = []
        for owner_id in owners:
            if owner_id == requestor_id:
                continue
            entries = self._filter_entries(owner_id, scope)
            if not entries:
                continue
            token = await self._ensure_token(requestor_id, owner_id, scope, reason)
            if not token:
                continue
            resource = self._build_resource(owner_id, entries, token)
            resources.append(resource)
        return resources

    async def _ensure_token(
        self,
        requestor_id: str,
        owner_id: str,
        scope: DiaryScope,
        reason: str,
    ) -> Optional[DiaryAccessToken]:
        key = (requestor_id, owner_id)
        async with self._lock:
            existing_id = self._active_grants.get(key)
            if existing_id:
                token = self._tokens.get(existing_id)
                if token and token.is_valid():
                    if token.scope.model_dump(mode="json") == scope.model_dump(mode="json"):
                        if self._reserve_use_locked(token):
                            return token
                self._drop_token_locked(existing_id)
        handler = self._handlers.get(owner_id)
        if not handler:
            raise DiaryPermissionError(f"No permission handler registered for agent {owner_id}")
        if owner_id in self._paused_owners:
            # Respect owner-level pause: do not mint new grants
            return None
        request = DiaryAccessRequest(
            requestor_id=requestor_id,
            owner_id=owner_id,
            reason=reason,
            scope=scope,
        )
        decision = await handler.approve(request)
        if not decision.approved:
            return None
        # Honor explicit 0; only fall back on None
        ttl = (
            int(self._token_ttl.total_seconds())
            if decision.expires_in_seconds is None
            else int(decision.expires_in_seconds)
        )
        # Compute expiry (None means no time window)
        expires_at: Optional[datetime]
        if ttl > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        else:
            expires_at = None

        # Uses: if decision specifies, use it; if ttl==0 and not specified, default to 1 (true one-shot)
        max_uses = decision.max_uses
        if max_uses is None and ttl == 0:
            max_uses = 1
        uses_remaining = max_uses
        token = DiaryAccessToken(
            token=str(uuid4()),
            request=request,
            scope=scope,
            expires_at=expires_at,
            max_uses=max_uses,
            uses_remaining=uses_remaining,
        )
        async with self._lock:
            self._tokens[token.token] = token
            self._active_grants[key] = token.token
            if not self._reserve_use_locked(token):
                self._active_grants.pop(key, None)
                return None
        return token

    def _reserve_use_locked(self, token: DiaryAccessToken) -> bool:
        if not token.is_valid():
            self._drop_token_locked(token.token)
            return False
        if token.uses_remaining is None:
            return True
        token.uses_remaining = max(0, token.uses_remaining - 1)
        if token.uses_remaining == 0:
            self._drop_token_locked(token.token)
        return True

    async def _prune_tokens(self) -> None:
        async with self._lock:
            stale_ids = [token_id for token_id, token in self._tokens.items() if not token.is_valid()]
            for token_id in stale_ids:
                self._drop_token_locked(token_id)

    def _drop_token_locked(self, token_id: str) -> None:
        self._tokens.pop(token_id, None)
        to_remove: list[Tuple[str, str]] = [
            key for key, active_id in self._active_grants.items() if active_id == token_id
        ]
        for key in to_remove:
            self._active_grants.pop(key, None)

    def _filter_entries(self, owner_id: str, scope: DiaryScope) -> List[DiaryEntry]:
        diary = self._diaries.get(owner_id)
        if not diary:
            return []
        entries = list(reversed(diary.entries))
        filtered: List[DiaryEntry] = []
        for entry in entries:
            if scope.tags and not set(scope.tags).intersection(entry.tags):
                continue
            if scope.life_indexes and entry.life_index not in scope.life_indexes:
                continue
            filtered.append(entry)
            if len(filtered) >= scope.limit:
                break
        return list(reversed(filtered))

    def _build_resource(
        self,
        owner_id: str,
        entries: Iterable[DiaryEntry],
        token: DiaryAccessToken,
    ) -> DiaryResource:
        profile = self._profiles.get(owner_id)
        owner_name = profile.display_name if profile else owner_id
        lines = [
            f"Shared diary excerpt from {owner_name} ({owner_id}) via MCP bus.",
            f"Scope: {token.scope.describe()} | Token: {token.token}",
        ]
        for entry in entries:
            tag_str = f" tags={','.join(entry.tags)}" if entry.tags else ""
            timestamp = entry.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            label = f"Entry #{entry.entry_index}" if entry.entry_index else "Entry"
            lines.append(
                f"- {label} from life {entry.life_index} at {timestamp}{tag_str}: {entry.text}"
            )
        text = "\n".join(lines)
        return DiaryResource(
            owner_id=owner_id,
            owner_display_name=owner_name,
            uri=f"mcp+diary://{owner_id}/{token.token}",
            text=text,
            entries=[entry.model_dump(mode="json") for entry in entries],
            annotations={
                "grantedAt": token.granted_at.isoformat(),
            "expiresAt": token.expires_at.isoformat() if token.expires_at else None,
            "scope": token.scope.model_dump(mode="json"),
            "maxUses": token.max_uses,
            "usesRemaining": token.uses_remaining,
        },
    )


__all__ = [
    "DiaryAccessDecision",
    "DiaryAccessRequest",
    "DiaryAccessToken",
    "DiaryPermissionError",
    "DiaryPermissionHandler",
    "DiaryResource",
    "DiaryScope",
    "SharedMCPBus",
]
