from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from control.controls import BY_ID, CONTROLS, MODES


@dataclass(frozen=True)
class Agent:
    enabled: bool
    usd_cap: float
    tools: frozenset[str]


@dataclass(frozen=True)
class Policy:
    profile: str
    loaded_at: str
    agents: dict[str, Agent]
    models: dict[str, float]
    trusted_hosts: frozenset[str]
    levels: dict[str, str]
    require_high_confidence: bool

    def level(self, name: str) -> str:
        return self.levels.get(name, "strict")


_cache: dict[str, Policy] = {}


def clear() -> None:
    _cache.clear()


def refresh(path: Path) -> Policy | None:
    key = str(path.resolve())
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return _cache.get(key)
    parsed = parse_policy(loaded)
    if parsed is None:
        return _cache.get(key)
    _cache[key] = parsed
    return parsed


def parse_policy(loaded: object) -> Policy | None:
    raw = _map(loaded)
    if raw is None:
        return None
    profile = _str(raw.get("profile"))
    agents, models = _agents(raw.get("agents")), _models(raw.get("models"))
    hosts = _str_list(raw.get("trusted_hosts"))
    controls = _map(raw.get("controls"))
    if None in (profile, agents, models, hosts) or controls is None:
        return None
    levels = _levels(controls)
    require_high_confidence = _flag(raw.get("require_high_confidence", False))
    if levels is None or require_high_confidence is None or profile is None or agents is None or models is None or hosts is None:
        return None
    return Policy(
        profile=profile,
        loaded_at=_now(),
        agents=agents,
        models=models,
        trusted_hosts=frozenset(hosts),
        levels=levels,
        require_high_confidence=require_high_confidence,
    )


def write_settings(
    path: Path,
    levels: dict[str, str],
    usd_cap: float,
    profile: str | None = None,
    require_high_confidence: bool = False,
) -> bool:
    if usd_cap < 0 or any(name not in BY_ID or mode not in MODES for name, mode in levels.items()):
        return False
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    raw = _map(loaded)
    if raw is None:
        return False
    raw.pop("mode", None)
    raw["require_high_confidence"] = require_high_confidence
    if profile is not None:
        raw["profile"] = profile
    agents = _map(raw.get("agents"))
    if agents is None:
        return False
    updated: dict[str, object] = {}
    for name, fields in agents.items():
        item = _map(fields)
        if item is None:
            return False
        item["usd_cap"] = usd_cap
        updated[name] = item
    raw["agents"] = updated
    controls = _map(raw.get("controls")) or {}
    controls.pop("budget", None)
    for name, mode in levels.items():
        controls[name] = {"mode": mode}
    raw["controls"] = controls
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    clear()
    return refresh(path) is not None


def _agents(value: object) -> dict[str, Agent] | None:
    raw = _map(value)
    if raw is None:
        return None
    agents: dict[str, Agent] = {}
    for name, item in raw.items():
        fields = _map(item)
        if fields is None:
            return None
        enabled = _bool(fields.get("enabled"))
        cap = _num(fields.get("usd_cap"))
        tools = _str_list(fields.get("tools"))
        if enabled is None or cap is None or tools is None:
            return None
        agents[name] = Agent(enabled, cap, frozenset(tools))
    return agents


def _models(value: object) -> dict[str, float] | None:
    raw = _map(value)
    if raw is None:
        return None
    models: dict[str, float] = {}
    for name, item in raw.items():
        fields = _map(item)
        if fields is None:
            return None
        price = _num(fields.get("usd_per_1k"))
        if price is None:
            return None
        models[name] = price
    return models


def _levels(value: object) -> dict[str, str] | None:
    raw = _map(value)
    if raw is None:
        return None
    levels: dict[str, str] = {}
    for item in CONTROLS:
        fields = _map(raw.get(item.id))
        if fields is None:
            return None
        mode = _str(fields.get("mode"))
        if mode not in MODES:
            return None
        levels[item.id] = mode
    return levels


def _map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        mapped[key] = item
    return mapped


def _str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        items.append(item)
    return items


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
