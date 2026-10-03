from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8000"


def main() -> None:
    fast = "--fast" in sys.argv
    scenes = json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))
    failed = 0
    with httpx.Client(timeout=60.0) as client:
        for scene in scenes:
            if fast and scene["live"]:
                continue
            failed += play(client, scene)
    if failed:
        raise SystemExit(f"{failed} scene(s) differed")


def play(client: httpx.Client, scene: dict[str, object]) -> int:
    agent = scene["agent"]
    body = scene["body"]
    if not isinstance(agent, str) or not isinstance(body, dict):
        raise SystemExit(f"{scene['id']} is missing agent or body")
    response = client.post(
        f"{BASE}/v1/chat/completions",
        headers={"X-Agent-Id": agent},
        json=body,
    )
    event = latest(client)
    code = error_code(response)
    decision = str(event.get("decision", ""))
    check = str(event.get("check", ""))
    print(f"{scene['title']}")
    print(f"  {scene['says']}")
    print(f"  {response.status_code}  {decision}  {check or code}{jev_text(event)}")
    expect = scene["expect"]
    if expect == "allow":
        ok = response.status_code == 200 and decision == "allow"
    elif expect == "redact":
        ok = response.status_code == 200 and decision == "redact"
    elif expect == "jev-or-allow":
        ok = decision == "allow" or check.startswith("jev.")
    else:
        ok = response.status_code == 403 and code == expect
    if not ok:
        print(f"  expected {expect}")
        return 1
    return 0


def latest(client: httpx.Client) -> dict[str, object]:
    payload: object = client.get(f"{BASE}/v1/report").json()
    if not isinstance(payload, dict):
        return {}
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return {}
    last = events[-1]
    if not isinstance(last, dict):
        return {}
    return {str(key): value for key, value in last.items()}


def error_code(response: httpx.Response) -> str:
    if response.status_code != 403:
        return ""
    payload: object = response.json()
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    code = error.get("code")
    return code if isinstance(code, str) else ""


def jev_text(event: dict[str, object]) -> str:
    scores = event.get("jev")
    if not isinstance(scores, dict) or not scores:
        return ""
    parts = [f"{name}={scores[name]}" for name in scores]
    return "  " + " ".join(parts)


if __name__ == "__main__":
    main()
