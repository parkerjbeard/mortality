from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .base import LLMMessage, LLMSession, TickToolName


def _normalize_content(content: LLMMessage) -> str | List[dict]:
    if isinstance(content.content, list):
        return content.content
    return str(content.content)


def _format_tool_as_text(message: LLMMessage) -> str:
    """Render tool emissions (like countdown ticks) into readable text."""

    payload = _normalize_content(message)
    if isinstance(payload, list):
        payload_text = json.dumps(payload)
    else:
        payload_text = payload
    label = message.name or "tool"
    if label == TickToolName:
        return f"[tick] {payload_text}"
    return f"[tool:{label}] {payload_text}"


def parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    """Best-effort JSON parsing for tool/function arguments."""

    if isinstance(raw, dict):
        return dict(raw)
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, list):
        # Allow list payloads by wrapping for downstream readability
        return {"items": raw}
    return {}


def to_openai_messages(session: LLMSession, new_messages: Sequence[LLMMessage]) -> List[dict]:
    """Convert internal messages into OpenAI chat schema."""

    conversation: List[dict] = []
    if session.config.system_prompt:
        conversation.append({"role": "system", "content": session.config.system_prompt})

    for message in [*session.history, *new_messages]:
        if message.role == "developer":
            conversation.append({"role": "system", "content": _normalize_content(message)})
        elif message.role == "tool":
            tool_call_id = _tool_call_id(message)
            if message.name != TickToolName:
                payload = {
                    "role": "tool",
                    "name": message.name or "tool",
                    "content": _ensure_text(message),
                }
                if tool_call_id:
                    payload["tool_call_id"] = tool_call_id
                conversation.append(payload)
            else:
                conversation.append(
                    {
                        "role": "user",
                        "name": message.name or "timer",
                        "content": _format_tool_as_text(message),
                    }
                )
        else:
            payload = {"role": message.role, "content": _normalize_content(message)}
            if message.role == "assistant":
                tool_calls = _openai_assistant_tool_calls(message)
                if tool_calls:
                    payload["tool_calls"] = tool_calls
            conversation.append(payload)

    return conversation


def to_anthropic_payload(
    session: LLMSession, new_messages: Sequence[LLMMessage]
) -> Tuple[Optional[str], List[dict]]:
    """Anthropic expects a detached system string + structured blocks."""

    system_block = session.config.system_prompt
    conversation: List[dict] = []
    for message in [*session.history, *new_messages]:
        if message.role in {"system", "developer"}:
            system_block = f"{system_block}\n{_ensure_text(message)}" if system_block else _ensure_text(message)
            continue
        if message.role == "tool":
            tool_call_id = _tool_call_id(message)
            if tool_call_id and message.name != TickToolName:
                conversation.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": _ensure_text(message),
                                    }
                                ],
                            }
                        ],
                    }
                )
            else:
                conversation.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": _format_tool_as_text(message),
                            }
                        ],
                    }
                )
            continue
        content_block = message.content
        if isinstance(content_block, list):
            content_parts = list(content_block)
        else:
            content_parts = [{"type": "text", "text": str(content_block)}]
        if message.role == "assistant":
            tool_uses = _anthropic_tool_use_blocks(message)
            if tool_uses:
                content_parts.extend(tool_uses)
        conversation.append({"role": message.role, "content": content_parts})
    return system_block, conversation


def to_gemini_contents(
    session: LLMSession, new_messages: Sequence[LLMMessage]
) -> Tuple[Optional[str], List[Dict[str, List[dict]]]]:
    """Convert messages into Gemini Developer API payloads."""

    system_instruction = session.config.system_prompt
    conversation: List[Dict[str, List[dict]]] = []
    for message in [*session.history, *new_messages]:
        if message.role in {"system", "developer"}:
            addition = _ensure_text(message)
            if system_instruction:
                system_instruction = f"{system_instruction}\n{addition}"
            else:
                system_instruction = addition
            continue
        parts = _parts_for_gemini(message)
        if not parts:
            continue
        mapped_role = "model" if message.role == "assistant" else "user"
        conversation.append({"role": mapped_role, "parts": parts})
    return system_instruction, conversation


def _parts_for_gemini(message: LLMMessage) -> List[dict]:
    if message.role == "tool":
        return [{"text": _format_tool_as_text(message)}]
    payload = message.content
    if isinstance(payload, list):
        normalized: List[dict] = []
        for item in payload:
            if isinstance(item, dict):
                normalized.append(item)
            elif item is not None:
                normalized.append({"text": str(item)})
        return normalized
    return [{"text": str(payload)}]


def _ensure_text(message: LLMMessage) -> str:
    if isinstance(message.content, list):
        return json.dumps(message.content)
    return str(message.content)


def _tool_call_id(message: LLMMessage) -> Optional[str]:
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("tool_call_id") or metadata.get("tool_use_id") or metadata.get("call_id")
    if value is None:
        return None
    return str(value)


def _assistant_tool_calls(message: LLMMessage) -> List[Dict[str, Any]]:
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    payload = metadata.get("tool_calls")
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for call in payload:
        if isinstance(call, dict):
            normalized.append(call)
    return normalized


def _call_identifier(call: Dict[str, Any]) -> Optional[str]:
    for key in ("call_id", "tool_call_id", "id"):
        value = call.get(key)
        if value:
            return str(value)
    return None


def _normalize_tool_arguments(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return parse_tool_arguments(raw)


def _openai_assistant_tool_calls(message: LLMMessage) -> List[Dict[str, Any]]:
    encoded: List[Dict[str, Any]] = []
    for call in _assistant_tool_calls(message):
        name = call.get("name")
        if not name:
            continue
        call_id = _call_identifier(call)
        if not call_id:
            continue
        arguments = _normalize_tool_arguments(call.get("arguments"))
        encoded.append(
            {
                "id": call_id,
                "type": call.get("type") or "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
        )
    return encoded


def _anthropic_tool_use_blocks(message: LLMMessage) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for call in _assistant_tool_calls(message):
        name = call.get("name")
        if not name:
            continue
        call_id = _call_identifier(call)
        if not call_id:
            continue
        arguments = _normalize_tool_arguments(call.get("arguments"))
        blocks.append(
            {
                "type": "tool_use",
                "id": call_id,
                "name": name,
                "input": arguments,
            }
        )
    return blocks


def _responses_tool_call_parts(message: LLMMessage) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    for call in _assistant_tool_calls(message):
        name = call.get("name")
        if not name:
            continue
        call_id = _call_identifier(call)
        if not call_id:
            continue
        arguments = _normalize_tool_arguments(call.get("arguments"))
        parts.append(
            {
                "type": "tool_call",
                "id": call_id,
                "tool_call_id": call_id,
                "name": name,
                "input": arguments,
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
        )
    return parts


RESPONSES_CONTENT_TYPES = {
    "assistant": "output_text",
    "system": "text",
    "developer": "text",
    "user": "input_text",
    "tool": "output_text",
}


def to_responses_input(
    session: LLMSession,
    new_messages: Sequence[LLMMessage],
    *,
    include_history: bool,
) -> List[Dict[str, Any]]:
    """Convert the conversation into Responses API message blocks."""

    conversation: List[LLMMessage] = []
    if include_history and session.history:
        conversation.extend(session.history)
    conversation.extend(new_messages)
    return [_message_to_responses_item(message) for message in conversation]


def _message_to_responses_item(message: LLMMessage) -> Dict[str, Any]:
    if message.role == "tool":
        tool_call_id = _tool_call_id(message)
        if tool_call_id:
            return {
                "role": "tool",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_call_id": tool_call_id,
                        "content": _normalize_responses_content("tool", message.content),
                    }
                ],
            }
        return {
            "role": "user",
            "content": [
                {
                    "type": RESPONSES_CONTENT_TYPES["user"],
                    "text": _format_tool_as_text(message),
                }
            ],
        }
    role = "system" if message.role == "developer" else message.role
    content = _normalize_responses_content(role, message.content)
    if role == "assistant":
        tool_calls = _responses_tool_call_parts(message)
        if tool_calls:
            content = [*content, *tool_calls]
    item: Dict[str, Any] = {"role": role, "content": content}
    if message.name:
        item["name"] = message.name
    return item


def _normalize_responses_content(role: str, content: str | List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if isinstance(content, list):
        return [_normalize_responses_part(role, part) for part in content]
    return [
        {
            "type": RESPONSES_CONTENT_TYPES.get(role, "input_text"),
            "text": str(content),
        }
    ]


def _normalize_responses_part(role: str, part: Any) -> Dict[str, Any]:
    if isinstance(part, dict):
        normalized = dict(part)
        normalized.setdefault("type", RESPONSES_CONTENT_TYPES.get(role, "input_text"))
        return normalized
    return {
        "type": RESPONSES_CONTENT_TYPES.get(role, "input_text"),
        "text": str(part),
    }


def stringify_openai_content(content: Any) -> str:
    """Flatten chat completion deltas/messages into plain text."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: List[str] = []
        for item in content:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, dict):
                if item.get("text_delta"):
                    fragments.append(str(item["text_delta"]))
                    continue
                refusal = item.get("refusal")
                if not refusal and isinstance(item.get("output"), dict):
                    refusal = item["output"].get("refusal")
                if refusal:
                    fragments.append(str(refusal))
                    continue
                if "text" in item:
                    fragments.append(stringify_openai_content(item["text"]))
                elif "content" in item:
                    fragments.append(stringify_openai_content(item["content"]))
            elif item is not None:
                fragments.append(str(item))
        return "".join(fragments)
    return str(content)
