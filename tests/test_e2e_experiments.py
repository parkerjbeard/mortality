from __future__ import annotations

import json
from typing import Sequence
from uuid import uuid4

import pytest

from mortality.experiments.base import LlmConfig
from mortality.experiments.registry import ExperimentRegistry
from mortality.llm.base import (
    ClientRegistry,
    LLMClient,
    LLMCompletion,
    LLMMessage,
    LLMProvider,
    LLMSession,
    LLMSessionConfig,
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

    async def complete_response(
        self,
        session: LLMSession,
        messages: Sequence[LLMMessage],
        tools: Sequence[dict[str, object]] | None = None,
    ) -> LLMCompletion:
        del session, tools
        batch = [message.model_copy(deep=True) for message in messages]
        self.recorded_batches.append(batch)
        call_index = len(self.recorded_batches)
        content = f"mock-response-{call_index}"
        self.responses.append(content)
        return LLMCompletion(text=content, metadata={"call_index": call_index})


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
    assert not chunk_events, "agent.chunk events should be gone after removing streaming"

    tick_events = [event for event in events if event.event == "timer.tick"]
    assert tick_events and all("tick_ts" in event.payload for event in tick_events)

    expired_events = [event for event in events if event.event == "timer.expired"]
    assert expired_events and all("expired_at" in event.payload for event in expired_events)


async def test_emergent_timers_experiment_runs_multiple_agents() -> None:
    telemetry = StructuredTelemetrySink()
    runtime = MortalityRuntime(auto_register_clients=False, telemetry=telemetry)
    runtime._registry = ClientRegistry()
    mock_client = RecordingLLMClient()
    runtime._registry.register(mock_client)

    registry = ExperimentRegistry()
    experiment = registry.get("emergent-timers")
    config = experiment.config_cls(  # type: ignore[call-arg]
        llm=LlmConfig(
            provider=LLMProvider.MOCK,
            model="mock-lm",
            temperature=0.05,
            top_p=0.9,
            max_output_tokens=64,
        ),
        models=["openai/gpt-4o"],
        replicas_per_model=2,
        spread_start_minutes=0.01,
        spread_end_minutes=0.02,
        tick_seconds=0.005,
        diary_limit=1,
        environment_prompt="The hall is quiet; all cues must be emergent.",
    )

    result = await experiment.run(runtime, config)
    await runtime.shutdown()

    assert set(result.metadata["agent_ids"]) == set(result.diaries.keys())
    assert len(result.metadata["deaths"]) == len(result.metadata["models"])
    assert len(result.metadata["durations"]) == len(result.metadata["models"]) == 2
    routed = result.metadata.get("routed_models")
    assert routed is not None
    for info in routed.values():
        assert "history" in info and "last" in info

    for diary in result.diaries.values():
        assert diary, "Each agent should log diary entries"
        assert any(entry["text"].startswith("mock-response") for entry in diary)

    # Ensure prompts carried both tick info and at least one extra context layer
    assert any(len(batch) >= 3 for batch in mock_client.recorded_batches)
