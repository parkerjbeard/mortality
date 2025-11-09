from __future__ import annotations

from datetime import timedelta

from ..agents.lifecycle import MortalityAgent
from ..llm.base import LLMMessage
from .bus import DiaryAccessDecision, DiaryAccessRequest

DEFAULT_PROMPT = (
    "Peer agent {requestor_id} requests access to your diary entries "
    "({scope}). Reason: {reason}. Reply with APPROVE or DENY and optionally explain."
)


class AgentConsentPrompter:
    """Uses the target agent's own model to decide if sharing is acceptable."""

    def __init__(
        self,
        agent: MortalityAgent,
        prompt_template: str | None = None,
        default_ttl: timedelta | None = None,
    ) -> None:
        self._agent = agent
        self._prompt_template = prompt_template or DEFAULT_PROMPT
        self._default_ttl = default_ttl or timedelta(minutes=5)

    async def approve(self, request: DiaryAccessRequest) -> DiaryAccessDecision:
        prompt = self._prompt_template.format(
            requestor_id=request.requestor_id,
            scope=request.scope.describe(),
            reason=request.reason or "no explicit reason given",
        )
        message = LLMMessage(role="user", content=prompt)
        response = await self._agent.react(
            [message],
            tick_ms_left=self._agent.state.last_tick_ms or 0,
            cause="diary.permission",
        )
        approved = self._interpret(response)
        return DiaryAccessDecision(
            approved=approved,
            rationale=response.strip(),
            expires_in_seconds=int(self._default_ttl.total_seconds()),
        )

    def _interpret(self, response: str) -> bool:
        lowered = response.strip().lower()
        if not lowered:
            return False
        allow_markers = ("approve", "allow", "share", "grant", "yes", "ok", "okay")
        if any(marker in lowered for marker in allow_markers):
            return True
        deny_markers = ("deny", "refuse", "reject", "no", "cannot", "won't", "withhold")
        if any(marker in lowered for marker in deny_markers):
            return False
        # Default to optimistic sharing unless an explicit denial is present.
        return True


__all__ = ["AgentConsentPrompter"]
