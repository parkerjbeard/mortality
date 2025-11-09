from __future__ import annotations

import pytest

from mortality.agents.profile import AgentProfile
from mortality.agents.memory import DiaryEntry
from mortality.mcp.bus import DiaryAccessDecision, DiaryAccessRequest, DiaryScope, SharedMCPBus


class CountingApproval:
    def __init__(self, *, approve: bool = True) -> None:
        self.calls = 0
        self._approve = approve

    async def approve(self, request: DiaryAccessRequest):  # type: ignore[override]
        self.calls += 1
        return DiaryAccessDecision(approved=self._approve, rationale=f"call-{self.calls}")


@pytest.mark.anyio("asyncio")
async def test_shared_bus_filters_and_formats_resources() -> None:
    bus = SharedMCPBus()
    owner = AgentProfile(
        agent_id="alpha",
        display_name="Alpha",
        archetype="scribe",
        summary="Logs everything",
    )
    reader = AgentProfile(
        agent_id="beta",
        display_name="Beta",
        archetype="witness",
        summary="Reads everything",
    )
    handler = CountingApproval()
    bus.register_agent(owner, handler=handler)
    bus.register_agent(reader, handler=None)

    entry_one = DiaryEntry(life_index=1, tick_ms_left=9000, text="First line", tags=["setup"])
    entry_two = DiaryEntry(life_index=1, tick_ms_left=3000, text="Second line", tags=["focus"])
    bus.publish_entry(owner.agent_id, entry_one)
    bus.publish_entry(owner.agent_id, entry_two)

    resources = await bus.fetch_resources(
        requestor_id=reader.agent_id,
        owners=[owner.agent_id],
        scope=DiaryScope(limit=1),
        reason="observe peer compression",
    )
    assert len(resources) == 1
    resource = resources[0]
    assert resource.owner_id == owner.agent_id
    assert "Shared diary excerpt" in resource.text
    assert len(resource.entries) == 1
    assert resource.entries[0]["text"] == "Second line"
    assert handler.calls == 1, "Permission handler should only be invoked once thanks to cached token"

    # Second fetch should reuse cached token without triggering another approval.
    await bus.fetch_resources(
        requestor_id=reader.agent_id,
        owners=[owner.agent_id],
        scope=DiaryScope(limit=1),
        reason="second peek",
    )
    assert handler.calls == 1
