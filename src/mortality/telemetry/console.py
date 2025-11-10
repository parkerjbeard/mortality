from __future__ import annotations

import io
import json
import os
import shutil
import sys
import threading
from datetime import datetime
from typing import Any, Dict, Iterable

try:  # pragma: no cover - optional dependency import
    from rich.console import Console
    from rich.markdown import Markdown
except Exception:  # pragma: no cover - rich not installed
    Console = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]

from .base import TelemetrySink


_LOCK = threading.Lock()


def _ansi_color(code: int) -> str:
    return f"\x1b[{code}m"


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"


class _ColorWheel:
    """Deterministic mapping from agent_id -> ANSI color code."""

    # High-contrast, readable foreground colors
    PALETTE: tuple[int, ...] = (
        36,  # cyan
        35,  # magenta
        33,  # yellow
        32,  # green
        34,  # blue
        91,  # bright red
        96,  # bright cyan
        95,  # bright magenta
        92,  # bright green
        94,  # bright blue
        93,  # bright yellow
    )

    def __init__(self) -> None:
        self._map: dict[str, int] = {}

    def get(self, key: str) -> int:
        if key in self._map:
            return self._map[key]
        idx = (abs(hash(key)) % len(self.PALETTE))
        code = self.PALETTE[idx]
        self._map[key] = code
        return code


def _fmt_ts(ts: str | None, show_ts: bool) -> str:
    if not show_ts:
        return ""
    if not ts:
        ts = datetime.now().isoformat(timespec="seconds")
    return f"{DIM}{ts}{RESET} "


def _fmt_agent(agent_id: str, wheel: _ColorWheel) -> str:
    return f"{BOLD}{_ansi_color(wheel.get(agent_id))}[{agent_id}]{RESET}"


def _truncate(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[: max(0, limit - 1)] + "…"
    return text


def _normalize_message_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [
            _normalize_message_content(part)
            for part in value
        ]
        return "\n\n".join(part for part in parts if part)
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        content = value.get("content")
        nested = _normalize_message_content(content)
        if nested:
            return nested
    return _safe_json(value)


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _normalize_for_compare(value: str) -> str:
    """Collapse whitespace for fuzzy equality comparisons."""

    if not value:
        return ""
    collapsed = " ".join(value.split())
    return collapsed.strip()


class ConsoleTelemetrySink(TelemetrySink):
    """Pretty, colorized CLI logger for long-running experiments.

    Controlled by env vars:
      - MORTALITY_CONSOLE_TRUNCATE: int chars for message bodies (default 400)
      - MORTALITY_CONSOLE_TIMESTAMPS: '1' to show timestamps (default 1)
      - MORTALITY_CONSOLE_TICKS: '1' to show every tick line (default 1)
      - MORTALITY_CONSOLE_SYSTEM: 'once' to show system messages once, 'all' (default 'once')
    """

    def __init__(self) -> None:
        self._wheel = _ColorWheel()
        self._stdout = sys.stdout
        # 0 disables truncation (default now off for readability)
        self._truncate = int(os.getenv("MORTALITY_CONSOLE_TRUNCATE", "0") or 0)
        self._show_ts = os.getenv("MORTALITY_CONSOLE_TIMESTAMPS", "1") != "0"
        self._show_ticks = os.getenv("MORTALITY_CONSOLE_TICKS", "1") != "0"
        self._system_mode = os.getenv("MORTALITY_CONSOLE_SYSTEM", "once").lower()
        self._seen_system: set[str] = set()
        self._code_theme = os.getenv("MORTALITY_CONSOLE_CODE_THEME", "monokai")
        self._rich_enabled = Console is not None and Markdown is not None
        # Track last outbound assistant utterance per agent to avoid echoing identical diary entries
        self._last_outbound_text: Dict[str, str] = {}

    # Public API from TelemetrySink
    def emit(self, event: str, payload: dict | None = None) -> None:  # pragma: no cover - console output
        data: Dict[str, Any] = payload or {}
        agent = data.get("agent_id", "?")
        label = _fmt_agent(agent, self._wheel)
        ts = data.get("ts") or data.get("tick_ts") or data.get("event_ts")
        prefix = f"{_fmt_ts(ts, self._show_ts)}{label} "

        line: str | None = None

        if event == "agent.spawned":
            sess = data.get("session") or {}
            model = sess.get("model", "?")
            provider = sess.get("provider", "?")
            line = f"{prefix}spawned ({provider}:{model})"

        elif event == "timer.started":
            if not self._show_ticks:
                return
            dur_ms = int(data.get("duration_ms", 0))
            tick_s = data.get("tick_seconds", 0)
            mins = int(dur_ms // 60000)
            secs = int((dur_ms % 60000) // 1000)
            line = f"{prefix}⏱ start {mins:02d}:{secs:02d} (tick {tick_s}s)"

        elif event == "timer.tick":
            if not self._show_ticks:
                return
            ms_left = int(data.get("ms_left", 0))
            t_m = ms_left // 60000
            t_s = (ms_left % 60000) // 1000
            idx = data.get("tick_index", 0)
            line = f"{prefix}· t-{int(t_m):02d}:{int(t_s):02d} (#{idx})"

        elif event == "agent.message":
            msg = data.get("message") or {}
            role = msg.get("role")
            direction = data.get("direction")
            content = msg.get("content")
            name = msg.get("name")

            # Suppress per-tick tool emission; timer.tick already logs cadence
            if role == "tool" and name:
                return

            if role == "system" and self._system_mode == "once":
                key = f"{agent}:system"
                if key in self._seen_system:
                    return
                self._seen_system.add(key)

            arrow = "⇣" if direction == "inbound" else "⇡"
            role_label = role or "message"
            header = f"{prefix}{arrow} {role_label}:"
            body_text = _normalize_message_content(content)
            if body_text:
                rendered = self._render_markdown(body_text, allow_truncate=True)
                indented = self._indent_block(rendered)
                line = f"{header}\n{indented}" if indented else header
            else:
                line = header

            if direction == "outbound" and role == "assistant":
                normalized = _normalize_for_compare(body_text)
                if normalized:
                    self._last_outbound_text[agent] = normalized
                else:
                    self._last_outbound_text.pop(agent, None)

        elif event == "agent.tool_call":
            meta = data.get("tool_call") or {}
            name = meta.get("name", "tool")
            line = f"{prefix}🔧 call {name}"

        elif event == "agent.tool_result":
            content = data.get("content")
            if content:
                body = _truncate(str(content), self._truncate)
                line = f"{prefix}🔧 result {body}"
            else:
                line = f"{prefix}🔧 result"

        elif event == "agent.diary_entry":
            entry_payload = data.get("entry") or {}
            body = str(entry_payload.get("text") or "")
            normalized = _normalize_for_compare(body)
            if normalized and normalized == self._last_outbound_text.get(agent):
                return
            idx = entry_payload.get("entry_index")
            created_at = entry_payload.get("created_at")
            stamp = created_at if isinstance(created_at, str) else None
            meta_bits = []
            if isinstance(idx, int) and idx > 0:
                meta_bits.append(f"#{idx}")
            if stamp:
                meta_bits.append(stamp)
            label = " " + " · ".join(meta_bits) if meta_bits else ""
            rendered = self._render_markdown(body, allow_truncate=False)
            indented = self._indent_block(rendered or body)
            line = f"{prefix}✎ diary{label}\n{indented}"

        elif event == "timer.expired":
            line = f"{prefix}✦ expired"

        elif event == "agent.death":
            line = f"{prefix}☠ died"

        elif event == "agent.respawn":
            life = data.get("life_index", 0)
            line = f"{prefix}↻ respawned (life {life})"

        if line is None:
            # Fallback for unknown events
            line = f"{prefix}{event} {json.dumps(data, ensure_ascii=False)}"

        with _LOCK:
            try:
                self._stdout.write(line + "\n")
                self._stdout.flush()
            except Exception:
                # Never let logging break the run
                pass

    def _render_markdown(self, text: str, *, allow_truncate: bool) -> str:
        cleaned = text.strip("\n")
        if not cleaned:
            return ""
        target = cleaned
        if allow_truncate and self._truncate:
            target = _truncate(cleaned, self._truncate)
        if not self._rich_enabled or Console is None or Markdown is None:
            return target
        console = Console(
            file=io.StringIO(),
            force_terminal=True,
            color_system="truecolor",
            width=self._terminal_width(),
            soft_wrap=True,
            highlight=False,
            markup=False,
        )
        try:
            with console.capture() as capture:
                console.print(Markdown(target, code_theme=self._code_theme))
            rendered = capture.get().rstrip()
            return rendered or target
        except Exception:
            # Never fail logging because rich formatting exploded
            return target

    def _indent_block(self, block: str) -> str:
        if not block:
            return ""
        indent = "    "
        return "\n".join(f"{indent}{line}" if line else indent for line in block.splitlines())

    def _terminal_width(self) -> int:
        try:
            columns = shutil.get_terminal_size((100, 20)).columns
        except OSError:
            columns = 100
        return max(columns, 60)


class MultiTelemetrySink(TelemetrySink):
    """Fan-out sink that emits to multiple sinks."""

    def __init__(self, sinks: Iterable[TelemetrySink]) -> None:
        self._sinks = list(sinks)

    def emit(self, event: str, payload: dict | None = None) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event, payload)
            except Exception:
                # Best-effort; keep other sinks alive
                pass

    def build_bundle(
        self,
        *,
        diaries: Dict[str, Any],
        metadata: Dict[str, Any],
        experiment: Dict[str, Any],
        config: Dict[str, Any],
        llm: Dict[str, Any],
        extra: Dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> Dict[str, Any]:
        for sink in self._sinks:
            build_bundle = getattr(sink, "build_bundle", None)
            if callable(build_bundle):
                return build_bundle(
                    diaries=diaries,
                    metadata=metadata,
                    experiment=experiment,
                    config=config,
                    llm=llm,
                    extra=extra,
                    system_prompt=system_prompt,
                )
        raise AttributeError(
            "MultiTelemetrySink requires at least one sink that implements build_bundle"
        )


__all__ = ["ConsoleTelemetrySink", "MultiTelemetrySink"]
