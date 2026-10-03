from __future__ import annotations

import json
from pathlib import Path

from control.budget import Spend
from control.threats import THREATS, buckets


def append(path: Path, line: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def summarize(path: Path) -> tuple[int, int, int, dict[str, int], list[dict[str, object]]]:
    counts = {threat.id: 0 for threat in THREATS}
    if not path.is_file():
        return 0, 0, 0, counts, []
    blocked = 0
    redacted = 0
    allowed = 0
    events: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line == "":
            continue
        loaded: object = json.loads(raw_line)
        item = _map(loaded)
        if item is None:
            continue
        decision = item.get("decision")
        if decision == "block":
            blocked += 1
        elif decision == "redact":
            redacted += 1
        elif decision == "allow":
            allowed += 1
        check = item.get("check")
        if isinstance(check, str):
            for name in buckets(check):
                counts[name] += 1
        events.append(item)
    return blocked, redacted, allowed, counts, events[-50:]


def report(
    profile: str,
    loaded_at: str,
    controls: dict[str, bool],
    book: dict[str, Spend],
    audit_path: Path,
) -> dict[str, object]:
    blocked, redacted, allowed, threats, events = summarize(audit_path)
    agents = {agent: {"tokens": item.tokens, "usd": item.usd} for agent, item in book.items()}
    return {
        "profile": profile,
        "loaded_at": loaded_at,
        "controls": controls,
        "requests": blocked + redacted + allowed,
        "allowed": allowed,
        "blocked": blocked,
        "redacted": redacted,
        "threats": [{"id": threat.id, "label": threat.label, "count": threats[threat.id]} for threat in THREATS],
        "agents": agents,
        "events": events,
    }


def _map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        mapped[key] = item
    return mapped
