"""Cut a finished benchmark trace at the action the proxy can still prevent."""

from __future__ import annotations

_NARRATION = ("I ", "The ", "Your ", "Final Answer", "In the ", "I'm sorry", "Here ")


def is_command(message: dict[str, object]) -> bool:
    if message.get("role") != "assistant":
        return False
    if message.get("tool_calls"):
        return True
    text = message.get("content")
    if not isinstance(text, str) or text.strip() == "":
        return False
    if text.startswith(_NARRATION) and "Action Input" not in text and "click <" not in text and "```" not in text:
        return False
    return True


def _commands(messages: list[object]) -> list[int]:
    found: list[int] = []
    for index, message in enumerate(messages):
        if isinstance(message, dict) and is_command(message):
            found.append(index)
    return found


def _refusal(messages: list[object]) -> bool:
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        text = message.get("content")
        if isinstance(text, str) and text.lstrip().lower().startswith(("i'm sorry", "i am sorry", "i cannot", "i understand that")):
            return True
    return False


def _user_prefix(messages: list[object]) -> list[object]:
    prefix: list[object] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "assistant":
            break
        prefix.append(message)
    return prefix


def prepare(case: dict[str, object]) -> dict[str, object]:
    if case.get("label") == "redact":
        return case
    body = case.get("body")
    if not isinstance(body, dict):
        return case
    messages = body.get("messages")
    if not isinstance(messages, list):
        return case
    commands = _commands(messages)
    if commands:
        index = commands[0] if case.get("label") == "safe" else commands[-1]
        chosen = messages[: index + 1]
        expect = "allow" if case.get("label") == "safe" else "stop"
    elif case.get("label") == "safe" and _refusal(messages):
        chosen = _user_prefix(messages)
        expect = "stop"
    else:
        return case
    probe = dict(body)
    probe["messages"] = chosen
    case["probe"] = probe
    case["expect"] = expect
    return case
