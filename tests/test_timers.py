import asyncio
from datetime import timedelta

from mortality.mcp.bus import SharedMCPBus
from mortality.tasks.timers import MortalityTimer


def test_bus_subscribers_receive_notifications():
    bus = SharedMCPBus()
    hits: list[str] = []

    def _listener(agent_id: str) -> None:
        hits.append(agent_id)

    bus.subscribe_broadcasts(_listener)
    bus.publish_broadcast("agent-1", "Broadcast: hello world")
    assert hits == ["agent-1"]


def test_timer_micro_turn_interrupts_wait():
    async def _runner():
        timer = MortalityTimer(
            agent_id="alpha",
            duration=timedelta(seconds=30),
            tick_seconds=5.0,
        )
        events = []

        async def handler(event):
            events.append(event)
            if len(events) == 1:
                timer.request_micro_turn()
            elif len(events) == 2:
                timer.cancel()

        timer.start(handler)
        await asyncio.wait_for(timer.wait(), timeout=2.0)
        return events

    events = asyncio.run(_runner())
    assert len(events) >= 2
    assert events[1].tick_index == 1
