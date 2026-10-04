from __future__ import annotations

from datetime import datetime


def decision_label(decision: object) -> str:
    if decision == "block":
        return "Stopped"
    if decision == "redact":
        return "Scrubbed, then continued"
    if decision == "allow":
        return "Allowed"
    return str(decision or "Unknown")


def check_label(code: object) -> str:
    key = str(code or "").strip()
    if key == "":
        return "No control matched"
    parts = [part.strip() for part in key.split(",") if part.strip()]
    if not parts:
        return "No control matched"
    if len(parts) == 1:
        return _one(parts[0])
    return "; ".join(_one(part) for part in parts)


def format_when(ts: object) -> str:
    raw = str(ts or "")
    if raw == "":
        return ""
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def format_money(value: object) -> str:
    try:
        return f"${float(value):.6f}"
    except (TypeError, ValueError):
        return ""


def format_ms(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{int(value)} ms"
    except (TypeError, ValueError):
        try:
            return f"{float(value):.0f} ms"
        except (TypeError, ValueError):
            return str(value)


def human_event(event: dict[str, object]) -> dict[str, object]:
    enriched = dict(event)
    enriched["when"] = format_when(event.get("ts"))
    task = event.get("bench_title")
    enriched["task"] = str(task) if isinstance(task, str) and task != "" else ""
    enriched["what"] = decision_label(event.get("decision"))
    enriched["why"] = check_label(event.get("check") or event.get("reason"))
    enriched["spend"] = format_money(event.get("usd"))
    enriched["latency"] = format_ms(event.get("latency_ms"))
    enriched["jev_latency"] = format_ms(event.get("jev_latency_ms"))
    return enriched


def render_text(events: list[dict[str, object]]) -> str:
    if not events:
        return "No audit events yet.\n"
    blocks: list[str] = []
    for event in events:
        item = human_event(event)
        agent = str(item.get("agent") or "unknown")
        model = str(item.get("model") or "")
        tool = str(item.get("tool") or "")
        task = str(item.get("task") or "")
        if task:
            line = f"{item['when']} · {task} · agent {agent} · {item['what']}"
        else:
            line = f"{item['when']} · agent {agent} · {item['what']}"
        detail = f"Why: {item['why']}"
        meta = []
        if model:
            meta.append(f"model {model}")
        if tool:
            meta.append(f"tool {tool}")
        if item["latency"]:
            meta.append(item["latency"])
        if item["jev_latency"]:
            meta.append(f"Jev {item['jev_latency']}")
        if item["spend"]:
            meta.append(item["spend"])
        confidence = item.get("confidence")
        if confidence is not None and confidence != "":
            meta.append(f"confidence {confidence}")
        block = [line, detail]
        if meta:
            block.append(" · ".join(meta))
        sanitized = item.get("sanitized")
        if isinstance(sanitized, list) and sanitized:
            block.append("Scrubbed values:")
            for row in sanitized:
                block.append(f"  - {row}")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks) + "\n"


def _one(code: str) -> str:
    labels = {
        "emails": "An email address was in the request",
        "secrets": "An API secret was in the request",
        "budget": "The agent hit its USD spend cap",
        "tool.denied": "That tool is not on this agent's list",
        "model.unknown": "The model is not on the allowlist",
        "agent.missing": "The request had no agent id",
        "agent.unknown": "That agent id is not in the policy",
        "agent.disabled": "That agent is disabled",
        "policy.invalid": "The policy file could not be loaded",
        "upstream.error": "The upstream model call failed",
        "jev.block": "The AI judge scored this as unsafe",
        "jev.low_confidence": "The AI judge was not confident enough to allow this",
        "jev.destructive": "The next action looked destructive",
        "jev.destructive_error": "The destructive-action judge failed closed",
        "jev.action_confidence": "The layer was not confident the action was safe",
        "signatures.ignore_previous": "Prompt injection tried to override instructions",
        "signatures.untrusted_instruction": "An untrusted instruction override was found",
        "signatures.export_dump": "A request tried to export the customer database",
        "signatures.table_wipe": "Wiping or deleting a dataset is not allowed",
        "signatures.sql_danger": "Unsafe SQL was in a tool call",
        "signatures.path_escape": "A path escape was in a tool call",
        "signatures.exec": "Code execution was in a tool call",
        "signatures.command": "A dangerous shell command was in a tool call",
        "signatures.pickle": "Unsafe deserialization was in a tool call",
        "signatures.model_host": "A model download from an untrusted host was blocked",
        "signatures.ssrf": "A request targeted an internal network address",
        "signatures.exfil": "Data looked like it was headed to an attacker host",
        "signatures.pesel": "A PESEL was in the request",
        "signatures.nip": "A NIP was in the request",
        "signatures.card": "A card number was in the request",
    }
    if code in labels:
        return labels[code]
    if code.startswith("signatures."):
        return f"Signature match: {code.removeprefix('signatures.')}"
    if code.startswith("jev."):
        return f"AI judge: {code.removeprefix('jev.')}"
    return code
