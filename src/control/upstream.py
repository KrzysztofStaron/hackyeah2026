from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

URL = "https://api.openai.com/v1/chat/completions"


@dataclass(frozen=True)
class UpstreamOk:
    status: int
    body: dict[str, object]


@dataclass(frozen=True)
class UpstreamErr:
    pass


def complete(body: dict[str, object], api_key: str) -> UpstreamOk | UpstreamErr:
    forwarded = dict(body)
    forwarded["stream"] = False
    try:
        response = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=forwarded,
            timeout=60.0,
        )
        payload: object = json.loads(response.text)
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return UpstreamErr()
    mapped = _map(payload)
    if mapped is None:
        return UpstreamErr()
    return UpstreamOk(response.status_code, mapped)


def _map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    mapped: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        mapped[key] = item
    return mapped
