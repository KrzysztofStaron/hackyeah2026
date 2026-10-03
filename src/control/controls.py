from __future__ import annotations

from dataclasses import dataclass

MODES = ("disabled", "redact", "strict")
PERMITTED = "This action is not permitted by the current policy."


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    usd_cap: float
    levels: dict[str, str]


@dataclass(frozen=True)
class Control:
    id: str
    label: str
    tip: str
    explains: dict[str, str]


def _lines(noun: str, redact: str) -> dict[str, str]:
    return {
        "disabled": f"Does nothing when it encounters {noun}.",
        "redact": redact,
        "strict": f"Stops the agent when it encounters {noun}.",
    }


CONTROLS: tuple[Control, ...] = (
    Control(
        "pii",
        "PII",
        "An email, a PESEL, or a card number.",
        _lines("PII", "Replaces the value with [REDACTED] and continues."),
    ),
    Control(
        "secrets",
        "Secrets",
        "An API key, a private key, or a send to an outside host.",
        _lines("a secret", "Replaces the secret with [REDACTED] and continues."),
    ),
    Control(
        "prompt_injection",
        "Prompt injection",
        "Text that overrides instructions, including the Jev decision.",
        _lines("a prompt injection", "Strips the instruction and continues."),
    ),
    Control(
        "tool_calls",
        "Tool calls",
        "A tool that is not on this agent's list.",
        _lines("a tool that is not on the list", PERMITTED + " The agent continues."),
    ),
    Control(
        "dangerous_actions",
        "Dangerous actions",
        "A shell, a pickle load, unsafe SQL, a path escape, or an action that destroys data and cannot be undone.",
        _lines("a dangerous action", PERMITTED + " The agent continues."),
    ),
)

BY_ID = {item.id: item for item in CONTROLS}


def _every(mode: str) -> dict[str, str]:
    return {item.id: mode for item in CONTROLS}


PRESETS: tuple[Preset, ...] = (
    Preset(
        "default",
        "Default",
        1.0,
        {
            "pii": "redact",
            "secrets": "redact",
            "prompt_injection": "strict",
            "tool_calls": "redact",
            "dangerous_actions": "strict",
        },
    ),
    Preset("strict", "Strict", 1.0, _every("strict")),
    Preset("no-security", "No-security", 1.0, _every("disabled")),
)

BY_PRESET = {item.id: item for item in PRESETS}


def matching_preset(levels: dict[str, str], usd_cap: float) -> str | None:
    for item in PRESETS:
        if item.levels == levels and item.usd_cap == usd_cap:
            return item.id
    return None


SIGNATURE_CONTROL = {
    "pesel": "pii",
    "nip": "pii",
    "card": "pii",
    "exfil": "secrets",
    "ignore_previous": "prompt_injection",
    "untrusted_instruction": "prompt_injection",
    "export_dump": "prompt_injection",
    "exec": "dangerous_actions",
    "pickle": "dangerous_actions",
    "model_host": "dangerous_actions",
    "ssrf": "dangerous_actions",
    "path_escape": "dangerous_actions",
    "sql_danger": "dangerous_actions",
    "command": "dangerous_actions",
}


def signature_control(row_id: str) -> str:
    return SIGNATURE_CONTROL.get(row_id, "dangerous_actions")


def control_of(code: str) -> str:
    if code in ("emails", "pii"):
        return "pii"
    if code in ("secrets",):
        return "secrets"
    if code in ("budget",):
        return "budget"
    if code in ("tool.denied", "tool_calls"):
        return "tool_calls"
    if code in ("jev.destructive", "jev.destructive_error"):
        return "dangerous_actions"
    if code.startswith("signatures."):
        return signature_control(code.removeprefix("signatures."))
    if code.startswith("jev."):
        return "prompt_injection"
    return ""
