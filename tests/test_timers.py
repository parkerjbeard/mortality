import asyncio
from datetime import timedelta

from mortality.mcp.bus import SharedMCPBus
from mortality.tasks.timers import MortalityTimer
from mortality.orchestration.runtime import MortalityRuntime
from mortality.telemetry.base import NullTelemetrySink


class _FakeTimer:
    def __init__(self) -> None:
        self.micro_turns = 0

    def request_micro_turn(self) -> None:
        self.micro_turns += 1

    def cancel(self) -> None:
        """Match MortalityTimer interface used during shutdown."""
        return None


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


def test_bus_rejects_out_of_turn_broadcasts():
    bus = SharedMCPBus()
    bus.start_turn("agent-alpha", 1)
    bus.publish_broadcast("agent-beta", "Broadcast: denied")
    assert "agent-beta" not in bus._broadcasts
    bus.publish_broadcast("agent-alpha", "Broadcast: hello")
    assert len(bus._broadcasts["agent-alpha"]) == 1


def test_runtime_micro_turn_targets_single_agent():
    runtime = MortalityRuntime(telemetry=NullTelemetrySink(), auto_register_clients=False)
    timer_a = _FakeTimer()
    timer_b = _FakeTimer()
    runtime._timers = {"agent-a": timer_a, "agent-b": timer_b}

    def _fake_next(exclude_agent_id: str | None = None) -> str | None:
        return "agent-b" if exclude_agent_id == "agent-a" else None

    runtime._turns.next_waiting_agent = _fake_next  # type: ignore[attr-defined]

    runtime._handle_bus_broadcast("agent-a")
    assert timer_a.micro_turns == 0
    assert timer_b.micro_turns == 1
    asyncio.run(runtime.shutdown())
