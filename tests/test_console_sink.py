import io

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
