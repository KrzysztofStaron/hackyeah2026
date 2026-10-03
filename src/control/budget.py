from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Spend:
    usd: float
    tokens: int
    calls: int = 0


def read(path: Path) -> dict[str, Spend]:
    if not path.is_file():
        return {}
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    raw = _map(loaded)
    if raw is None:
        return {}
    book: dict[str, Spend] = {}
    for agent, item in raw.items():
        fields = _map(item)
        if fields is None:
            continue
        usd = fields.get("usd")
        tokens = fields.get("tokens")
        calls = fields.get("calls", 0)
        if isinstance(usd, bool) or not isinstance(usd, (int, float)):
            continue
        if isinstance(tokens, bool) or not isinstance(tokens, int):
            continue
        if isinstance(calls, bool) or not isinstance(calls, int):
            calls = 0
        book[agent] = Spend(float(usd), tokens, calls)
    return book


def write(path: Path, book: dict[str, Spend]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        agent: {"usd": item.usd, "tokens": item.tokens, "calls": item.calls} for agent, item in book.items()
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def _map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        mapped[key] = item
    return mapped
