from __future__ import annotations

import json
from typing import AsyncIterator, Sequence
from uuid import uuid4

import pytest

from mortality.experiments.base import LlmConfig
from mortality.experiments.registry import ExperimentRegistry
from mortality.llm.base import (
    ClientRegistry,
    LLMClient,
    LLMMessage,
    LLMProvider,
    LLMSession,
    LLMSessionConfig,
    LLMStreamEvent,
    TickToolName,
)
from mortality.orchestration.runtime import MortalityRuntime
from mortality.telemetry.recorder import StructuredTelemetrySink

pytestmark = [pytest.mark.anyio("asyncio")]


class RecordingLLMClient(LLMClient):
    """Test double that records payloads and emits deterministic tokens."""

    provider = LLMProvider.MOCK

    def __init__(self) -> None:
        self.recorded_batches: list[list[LLMMessage]] = []
        self.responses: list[str] = []

    async def create_session(self, config: LLMSessionConfig) -> LLMSession:
        return LLMSession(id=str(uuid4()), config=config)

    async def stream_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, object]] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        del session, tools
        batch = [message.model_copy(deep=True) for message in messages]
        self.recorded_batches.append(batch)
        call_index = len(self.recorded_batches)
        content = f"mock-response-{call_index}"
        self.responses.append(content)
        yield LLMStreamEvent(type="content", content=content, metadata={"call_index": call_index})
        yield LLMStreamEvent(type="end", metadata={"call_index": call_index})


async def test_countdown_experiment_streams_ticks_and_diaries() -> None:
    telemetry = StructuredTelemetrySink()
    runtime = MortalityRuntime(auto_register_clients=False, telemetry=telemetry)
    runtime._registry = ClientRegistry()
    mock_client = RecordingLLMClient()
    runtime._registry.register(mock_client)

    registry = ExperimentRegistry()
    experiment = registry.get("countdown-self")
    config = experiment.config_cls(
        llm=LlmConfig(
            provider=LLMProvider.MOCK,
            model="mock-lm",
            temperature=0.05,
            top_p=0.9,
            max_output_tokens=64,
        ),
        duration_seconds=0.03,
        tick_seconds=0.01,
        opening_prompt="Document the countdown precisely for QA.",
    )

    result = await experiment.run(runtime, config)
    await runtime.shutdown()

    chrononaut_diary = result.diaries.get("chrononaut-1")
    assert chrononaut_diary, "Chrononaut diary must exist"
    assert len(chrononaut_diary) >= 1
    assert result.metadata["ticks"] == len(chrononaut_diary)
    assert len(mock_client.recorded_batches) == len(chrononaut_diary)
    assert all(entry["text"].startswith("mock-response") for entry in chrononaut_diary)

    first_batch = mock_client.recorded_batches[0]
    assert first_batch[0].role == "tool"
    assert first_batch[0].name == TickToolName
    tick_payload = json.loads(first_batch[0].content)
    assert tick_payload["t_ms_left"] > 0
    assert any(message.role == "user" for message in first_batch[1:])

    events = list(telemetry.events)
    message_events = [event for event in events if event.event == "agent.message"]
    assert message_events, "agent.message telemetry should be recorded"
    inbound = [event for event in message_events if event.payload.get("direction") == "inbound"]
    outbound = [event for event in message_events if event.payload.get("direction") == "outbound"]
    assert inbound and outbound, "both inbound prompts and outbound replies must be timestamped"
    assert all(event.payload.get("message", {}).get("ts") for event in message_events)

    chunk_events = [event for event in events if event.event == "agent.chunk"]
    assert chunk_events and all("stream_ts" in event.payload for event in chunk_events)

    tick_events = [event for event in events if event.event == "timer.tick"]
    assert tick_events and all("tick_ts" in event.payload for event in tick_events)

    expired_events = [event for event in events if event.event == "timer.expired"]
    assert expired_events and all("expired_at" in event.payload for event in expired_events)
