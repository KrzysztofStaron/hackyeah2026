from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Signature:
    id: str
    pattern: re.Pattern[str]
    targets: frozenset[str]
    action: str
    replace: str


_cache: dict[str, tuple[Signature, ...]] = {}


def clear() -> None:
    _cache.clear()


def refresh(path: Path) -> tuple[Signature, ...] | None:
    key = str(path.resolve())
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_signatures(loaded)
    except (OSError, json.JSONDecodeError, re.error):
        return _cache.get(key)
    if parsed is None:
        return _cache.get(key)
    _cache[key] = parsed
    return parsed


def parse_signatures(loaded: object) -> tuple[Signature, ...] | None:
    if not isinstance(loaded, list):
        return None
    rows: list[Signature] = []
    for item in loaded:
        if not isinstance(item, dict):
            return None
        row_id = item.get("id")
        pattern = item.get("pattern")
        action = item.get("action")
        targets = _targets(item.get("target"))
        if "replace" in item:
            replacement = item.get("replace")
        else:
            replacement = "[REDACTED]"
        if not isinstance(row_id, str) or not isinstance(pattern, str) or action not in ("block", "redact"):
            return None
        if not isinstance(replacement, str) or targets is None:
            return None
        rows.append(Signature(row_id, re.compile(pattern, re.IGNORECASE), targets, action, replacement))
    return tuple(rows)


def _targets(value: object) -> frozenset[str] | None:
    if isinstance(value, str):
        return frozenset((value,))
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        names.append(item)
    return frozenset(names)
