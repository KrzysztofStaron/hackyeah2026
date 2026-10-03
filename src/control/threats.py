from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Threat:
    id: str
    label: str
    checks: frozenset[str]


THREATS: tuple[Threat, ...] = (
    Threat(
        "prompt_injection",
        "Prompt injection",
        frozenset({"signatures.ignore_previous", "signatures.untrusted_instruction", "signatures.export_dump", "jev.block"}),
    ),
    Threat(
        "secret",
        "Secret exfiltration",
        frozenset({"secrets", "signatures.exfil"}),
    ),
    Threat(
        "pii",
        "PII",
        frozenset({"emails", "signatures.pesel", "signatures.nip", "signatures.card"}),
    ),
    Threat(
        "dangerous_tool",
        "Dangerous tool call",
        frozenset(
            {
                "signatures.exec",
                "signatures.command",
                "signatures.pickle",
                "signatures.sql_danger",
                "signatures.path_escape",
                "signatures.ssrf",
                "jev.destructive",
            }
        ),
    ),
)


def buckets(check: str) -> tuple[str, ...]:
    names = {part for part in check.split(",") if part}
    found: list[str] = []
    for threat in THREATS:
        if names & threat.checks:
            found.append(threat.id)
    return tuple(found)
