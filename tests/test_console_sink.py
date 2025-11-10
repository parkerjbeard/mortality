import io
import json

from mortality.telemetry.console import ConsoleTelemetrySink


def make_sink():
    sink = ConsoleTelemetrySink()
    sink._stdout = io.StringIO()
    # Stabilize tests by hiding timestamps (they only affect prefixes)
    sink._show_ts = False
    return sink


def message_payload(text: str) -> dict:
    return {
        "agent_id": "washington",
        "direction": "outbound",
        "message": {
            "role": "assistant",
            "content": text,
        },
    }


def diary_payload(text: str, index: int = 2) -> dict:
    return {
        "agent_id": "washington",
        "entry": {
            "text": text,
            "entry_index": index,
            "created_at": "2025-11-10T07:40:24.229037Z",
        },
    }


def peer_timer_tool_result_payload(
    overrides: dict[str, float] | None = None,
) -> dict:
    content = {
        "viewer_id": "madison",
        "queried": ["washington", "franklin"],
        "timers": [
            {"display_name": "Washington", "seconds_left": 263.115, "status": "active"},
            {"display_name": "Franklin", "seconds_left": 600.087, "status": "active"},
            {"display_name": "Jefferson", "seconds_left": 833.024, "status": "active"},
        ],
    }
    if overrides:
        for timer in content["timers"]:
            name = timer.get("display_name")
            if name in overrides:
                timer["seconds_left"] = overrides[name]
    return {
        "agent_id": "washington",
        "tool_call": {"name": "peer_timer_status"},
        "content": json.dumps(content),
    }


def test_console_sink_omits_duplicate_diary_lines():
    sink = make_sink()
    sink.emit("agent.message", message_payload("My countdown timer just updated."))
    sink.emit("agent.diary_entry", diary_payload("My countdown timer just updated."))
    output = sink._stdout.getvalue()
    assert output.count("My countdown timer just updated.") == 1
    assert "✎ diary" not in output


def test_console_sink_renders_unique_diary_entries():
    sink = make_sink()
    sink.emit("agent.message", message_payload("My countdown timer just updated."))
    sink.emit(
        "agent.diary_entry",
        diary_payload("My diary reflection diverges from my broadcast."),
    )
    output = sink._stdout.getvalue()
    assert output.count("✎ diary") == 1
    assert "My diary reflection diverges from my broadcast." in output


def test_console_sink_summarizes_peer_timer_status():
    sink = make_sink()
    sink.emit("agent.tool_result", peer_timer_tool_result_payload())
    output = sink._stdout.getvalue()
    assert "peer_timer_status → Washington: constrained, 0s" in output
    assert "Franklin: steady, 0s" in output
    assert "{\"viewer_id\"" not in output


def test_console_sink_stashes_raw_tool_results():
    sink = make_sink()
    payload = peer_timer_tool_result_payload()
    sink.emit("agent.tool_result", payload)
    stash = sink.stashed_tool_results()
    assert stash, "expected raw tool results to be stashed"
    record = stash[-1]
    assert record["tool_call"]["name"] == "peer_timer_status"
    assert record["content"] == payload["content"]


def test_console_sink_reports_timer_deltas():
    sink = make_sink()
    sink.emit("agent.tool_result", peer_timer_tool_result_payload())
    updated = peer_timer_tool_result_payload({"Washington": 200.0})
    sink.emit("agent.tool_result", updated)
    output = sink._stdout.getvalue().strip().splitlines()[-1]
    assert "Washington: constrained, -63s" in output
