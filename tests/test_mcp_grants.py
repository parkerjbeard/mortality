from __future__ import annotations

import pytest

from mortality.agents.profile import AgentProfile
from mortality.agents.memory import DiaryEntry
from mortality.mcp.bus import (
    DiaryAccessDecision,
    DiaryAccessRequest,
    DiaryScope,
    SharedMCPBus,
)


class OneShotApproval:
    """Approves with explicit 0-second TTL and no max_uses set.

    Bus should treat this as a one-shot grant (uses=1) without time window.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def approve(self, request: DiaryAccessRequest):  # type: ignore[override]
        self.calls += 1
        return DiaryAccessDecision(
            approved=True,
            rationale="one-shot",
            expires_in_seconds=0,
        )


@pytest.mark.anyio("asyncio")
async def test_zero_ttl_is_single_use_not_default_ttl() -> None:
    bus = SharedMCPBus()
    owner = AgentProfile(agent_id="owner", display_name="Owner", archetype="scribe", summary="")
    reader = AgentProfile(agent_id="reader", display_name="Reader", archetype="witness", summary="")
    handler = OneShotApproval()
    bus.register_agent(owner, handler=handler)
    bus.register_agent(reader, handler=None)

    # Publish two entries
    bus.publish_entry(owner.agent_id, DiaryEntry(life_index=1, tick_ms_left=5000, text="A", tags=["x"]))
    bus.publish_entry(owner.agent_id, DiaryEntry(life_index=1, tick_ms_left=1000, text="B", tags=["y"]))

    # First fetch should approve and consume the single use
    res1 = await bus.fetch_resources(
        requestor_id=reader.agent_id,
        owners=[owner.agent_id],
        scope=DiaryScope(limit=1),
        reason="peek",
    )
    assert len(res1) == 1
    assert handler.calls == 1

    # Second fetch should require a fresh approval because previous grant had uses=0
    res2 = await bus.fetch_resources(
        requestor_id=reader.agent_id,
        owners=[owner.agent_id],
        scope=DiaryScope(limit=1),
        reason="peek-again",
    )
    assert len(res2) == 1
    assert handler.calls == 2


class CountingApproval:
    def __init__(self) -> None:
        self.calls = 0

    async def approve(self, request: DiaryAccessRequest):  # type: ignore[override]
        self.calls += 1
        return DiaryAccessDecision(approved=True, rationale="ok")


@pytest.mark.anyio("asyncio")
async def test_paused_owner_blocks_new_grants() -> None:
    bus = SharedMCPBus()
    owner = AgentProfile(agent_id="alpha", display_name="Alpha", archetype="scribe", summary="")
    reader = AgentProfile(agent_id="beta", display_name="Beta", archetype="witness", summary="")
    handler = CountingApproval()
    bus.register_agent(owner, handler=handler)
    bus.register_agent(reader, handler=None)
    bus.publish_entry(owner.agent_id, DiaryEntry(life_index=1, tick_ms_left=1000, text="X", tags=["t"]))

    # Pause before any grants are minted
    bus.pause_owner(owner.agent_id, True)

    res = await bus.fetch_resources(
        requestor_id=reader.agent_id,
        owners=[owner.agent_id],
        scope=DiaryScope(limit=1),
        reason="should-be-blocked",
    )
    assert res == []
    assert handler.calls == 0
