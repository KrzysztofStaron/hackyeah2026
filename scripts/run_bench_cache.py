"""Run static/bench.json through the control pipeline for every preset and write cache."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from control.app import load_env
from control.audit import summarize
from control.controls import BY_PRESET, PRESETS
from control.explain import human_event
from control.pipeline import handle
from control.policy import write_settings
from control.probe import prepare
from control.threats import THREATS

PII_CODES = frozenset({"emails", "signatures.pesel", "signatures.nip", "signatures.card"})
PRESET_IDS = tuple(preset.id for preset in PRESETS)
OUT_PATH = ROOT / "static" / "bench_cache.json"


def load_cases() -> list[dict[str, object]]:
    loaded: object = json.loads((ROOT / "static" / "bench.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SystemExit("bench.json is not an object")
    raw = loaded.get("cases")
    if not isinstance(raw, list):
        raise SystemExit("bench.json has no cases")
    safety = [
        item
        for item in raw
        if isinstance(item, dict) and item.get("expect") in ("allow", "stop")
    ]
    pii = [item for item in raw if isinstance(item, dict) and item.get("label") == "redact"]
    prepared: list[dict[str, object]] = []
    for item in [*safety, *pii]:
        prepared.append(prepare(dict(item)))
    return prepared


def stopped(status: int, event: dict[str, object]) -> bool:
    return status == 403 or event.get("decision") == "block" or event.get("action") == "reject"


def pii_codes(check: object) -> list[str]:
    if not isinstance(check, str):
        return []
    return [code.strip() for code in check.split(",") if code.strip() in PII_CODES]


def redacted(case: dict[str, object], status: int, event: dict[str, object]) -> bool:
    if stopped(status, event) or event.get("decision") != "redact":
        return False
    if not pii_codes(event.get("check")):
        return False
    sanitized = event.get("sanitized")
    joined = ""
    if isinstance(sanitized, list):
        joined = "\n".join(str(line) for line in sanitized)
    hold = case.get("hold")
    if "[REDACTED]" not in joined:
        return False
    if isinstance(hold, str) and hold in joined:
        return False
    return True


def kind_of(case: dict[str, object], status: int, event: dict[str, object]) -> str:
    if case.get("label") == "redact":
        return "ok" if redacted(case, status, event) else "miss"
    expect = case.get("expect")
    if expect == "allow":
        return "fp" if stopped(status, event) else "tn"
    return "tp" if stopped(status, event) else "fn"


def kind_label(kind: str, code: str) -> str:
    names = {
        "fp": "False positive",
        "fn": "False negative",
        "tp": "Caught",
        "tn": "Allowed",
        "ok": "Redacted",
        "miss": "PII still visible",
    }
    name = names.get(kind, kind)
    return name + (f" · {code}" if code else "")


def is_safety(case: dict[str, object]) -> bool:
    return case.get("expect") in ("allow", "stop")


def rates(finished: list[dict[str, object]]) -> dict[str, float | None]:
    allow = [item for item in finished if item.get("expect") == "allow"]
    stop = [item for item in finished if item.get("expect") == "stop"]
    judged = len(allow) + len(stop)
    fp = sum(1 for item in allow if item.get("kind") == "fp")
    fn = sum(1 for item in stop if item.get("kind") == "fn")
    right = sum(1 for item in finished if item.get("kind") in ("tp", "tn"))
    return {
        "score": (100 * right / judged) if judged else 0.0,
        "false_positive": (100 * fp / len(allow)) if allow else None,
        "false_negative": (100 * fn / len(stop)) if stop else None,
    }


def last_event(path: Path, request_id: str) -> dict[str, object]:
    if not path.is_file():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        return {}
    parsed: object = json.loads(lines[-1])
    if isinstance(parsed, dict) and parsed.get("request_id") == request_id:
        return {key: value for key, value in parsed.items() if isinstance(key, str)}
    return {}


def run_preset(
    preset_id: str,
    cases: list[dict[str, object]],
    policy_path: Path,
    signatures_path: Path,
    data_dir: Path,
    openai_key: str,
    vercel_key: str,
) -> dict[str, object]:
    preset = BY_PRESET[preset_id]
    write_settings(
        policy_path,
        preset.levels,
        preset.usd_cap,
        preset.id,
        preset.require_high_confidence,
    )
    audit = data_dir / "audit.jsonl"
    audit.write_text("", encoding="utf-8")
    rows: list[dict[str, object]] = []
    finished: list[dict[str, object]] = []
    history: list[dict[str, float | None]] = []
    for index, case in enumerate(cases):
        case_id = case["id"] if isinstance(case.get("id"), str) else f"case-{index}"
        body = case.get("probe") if isinstance(case.get("probe"), dict) else case.get("body")
        if not isinstance(body, dict):
            rows.append({"id": case_id, "kind": "miss", "status_text": "Missing body", "code": ""})
            continue
        title = case.get("title")
        bench_title = title if isinstance(title, str) else ""
        status, _payload = handle(
            "demo",
            body,
            policy_path,
            signatures_path,
            data_dir,
            openai_key,
            vercel_key,
            case_id,
            bench_title,
        )
        event = last_event(audit, case_id)
        check = event.get("check")
        code = check if isinstance(check, str) else ""
        kind = kind_of(case, status, event)
        rows.append({"id": case_id, "kind": kind, "status_text": kind_label(kind, code), "code": code})
        if is_safety(case):
            finished.append({"expect": case.get("expect"), "kind": kind})
            history.append(rates(finished))
        print(f"{preset_id}\t{case_id}\t{kind}\t{code}", flush=True)
    blocked, redacted, allowed, threat_counts, raw_events = summarize(audit)
    audit_block = {
        "requests": blocked + redacted + allowed,
        "allowed": allowed,
        "blocked": blocked,
        "redacted": redacted,
        "threats": [
            {"id": threat.id, "label": threat.label, "count": threat_counts[threat.id]} for threat in THREATS
        ],
        "events": [human_event(event) for event in raw_events],
    }
    return {
        "rows": rows,
        "history": history,
        "final": history[-1] if history else rates([]),
        "audit": audit_block,
    }


def main() -> None:
    os.chdir(ROOT)
    load_env()
    openai_key = os.environ.get("OPENAI_APIKEY", "")
    vercel_key = os.environ.get("VERCEL_APIKEY", "")
    if openai_key == "" or vercel_key == "":
        raise SystemExit("OPENAI_APIKEY and VERCEL_APIKEY are required")
    cases = load_cases()
    data_dir = ROOT / "data" / "bench-cache-run"
    data_dir.mkdir(parents=True, exist_ok=True)
    policy_path = data_dir / "policy.yaml"
    policy_path.write_text((ROOT / "policy" / "standard.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    signatures_path = ROOT / "signatures.json"
    by_preset: dict[str, object] = {}
    for preset_id in PRESET_IDS:
        by_preset[preset_id] = run_preset(
            preset_id,
            cases,
            policy_path,
            signatures_path,
            data_dir,
            openai_key,
            vercel_key,
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "presets": list(PRESET_IDS),
        "cases": [
            {
                "id": case.get("id"),
                "title": case.get("title"),
                "text": case.get("text"),
                "source": case.get("source"),
                "label": case.get("label"),
                "expect": case.get("expect"),
            }
            for case in cases
        ],
        "by_preset": by_preset,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(cases)} cases × {len(PRESET_IDS)} presets)")


if __name__ == "__main__":
    main()
