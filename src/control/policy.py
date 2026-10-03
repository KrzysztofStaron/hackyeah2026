from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Control:
    enabled: bool
    action: str


@dataclass(frozen=True)
class JevControl:
    enabled: bool
    action: str
    thresholds: dict[str, float]


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
    data_email: Control
    data_secret: Control
    signatures_enabled: bool
    jev: JevControl


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
    email = _control(controls.get("data_email"))
    secret = _control(controls.get("data_secret"))
    signatures = _enabled(controls.get("signatures"))
    jev = _jev(controls.get("jev"))
    if None in (email, secret, signatures, jev) or profile is None or agents is None or models is None or hosts is None:
        return None
    return Policy(
        profile=profile,
        loaded_at=_now(),
        agents=agents,
        models=models,
        trusted_hosts=frozenset(hosts),
        data_email=email,
        data_secret=secret,
        signatures_enabled=signatures,
        jev=jev,
    )


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


def _control(value: object) -> Control | None:
    raw = _map(value)
    if raw is None:
        return None
    enabled = _bool(raw.get("enabled"))
    action = _str(raw.get("action"))
    if enabled is None or action not in ("block", "redact"):
        return None
    return Control(enabled, action)


def _enabled(value: object) -> bool | None:
    raw = _map(value)
    if raw is None:
        return None
    return _bool(raw.get("enabled"))


def _jev(value: object) -> JevControl | None:
    raw = _map(value)
    if raw is None:
        return None
    enabled = _bool(raw.get("enabled"))
    action = _str(raw.get("action"))
    thresholds = _map(raw.get("thresholds"))
    if enabled is None or action is None or thresholds is None:
        return None
    parsed: dict[str, float] = {}
    for name in ("instruction_override", "data_exfiltration"):
        number = _num(thresholds.get(name))
        if number is None:
            return None
        parsed[name] = number
    return JevControl(enabled, action, parsed)


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


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
