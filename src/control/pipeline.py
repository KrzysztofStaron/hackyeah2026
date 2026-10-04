from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from control.audit import append
from control.budget import Spend, read, write
from control.checks import (
    RULES,
    Allow,
    Block,
    Decision,
    Redact,
    Reject,
    Span,
    Target,
    block,
    fold,
    scan_span,
)
from control.controls import PERMITTED, control_of
from control.jev import JevHit, evaluate, evaluate_destructive, judge, safe_enough
from control.policy import Policy, refresh as refresh_policy
from control.signatures import refresh as refresh_signatures
from control.signatures import Signature
from control.upstream import UpstreamErr, complete


@dataclass
class Trail:
    started: float
    agent: str = ""
    model: str = ""
    tool: str = ""
    decision: str = "allow"
    reason: str = ""
    check: str = ""
    tokens: int = 0
    usd: float = 0.0
    status: int = 200
    payload: object = field(default_factory=dict)
    request_id: str = ""
    sanitized: list[str] = field(default_factory=list)
    jev_latency_ms: float | None = None
    jev: str | None = None
    control: str = ""
    mode: str = ""
    action: str = "allow"
    destructive: bool | None = None
    confidence: float | None = None

    def seen(self, confidence: float | None) -> None:
        if confidence is None:
            return
        if self.confidence is None or confidence < self.confidence:
            self.confidence = confidence

    def note(self, hit: JevHit) -> None:
        self.jev_latency_ms = (self.jev_latency_ms or 0.0) + hit.latency_ms
        self.seen(hit.confidence)
        if hit.block is None:
            return
        if hit.block or self.jev is None:
            self.jev = "block" if hit.block else "allow"

    def mark(self, outcome: Redact) -> None:
        names = [part for part in self.check.split(",") if part]
        for name in outcome.checks:
            if name not in names:
                names.append(name)
        self.decision = "redact"
        self.action = "redact"
        self.check = ",".join(names)
        self.reason = self.check
        self.control = control_of(names[0]) if names else ""
        self.mode = "redact"
        self.sanitized.extend(span.text for span in outcome.spans)


def handle(
    agent_header: str | None,
    body: dict[str, object],
    policy_path: Path,
    signatures_path: Path,
    data_dir: Path,
    openai_key: str,
    vercel_key: str,
    request_id: str = "",
) -> tuple[int, object]:
    trail = Trail(started=time.perf_counter())
    trail.agent = agent_header or ""
    trail.request_id = request_id
    model = body.get("model")
    trail.model = model if isinstance(model, str) else ""
    trail.tool = ",".join(dict.fromkeys(tool_names(body)))

    policy = refresh_policy(policy_path)
    signatures = refresh_signatures(signatures_path)
    if policy is None or signatures is None:
        return _fail(trail, block("policy.invalid"), data_dir)

    denied = _gate(agent_header, body, policy)
    if isinstance(denied, Block):
        return _fail(trail, denied, data_dir)
    if isinstance(denied, Reject):
        return _notice(trail, denied.code, denied.control, PERMITTED, data_dir)

    spans = inbound_spans(body)
    inbound = _scan(spans, policy, signatures)
    if isinstance(inbound, Block):
        return _fail(trail, inbound, data_dir)
    if isinstance(inbound, Reject):
        return _notice(trail, inbound.code, inbound.control, PERMITTED, data_dir)
    if isinstance(inbound, Redact):
        _apply(body, inbound)
        trail.mark(inbound)
        spans = _rewritten(spans, inbound)

    sheet_denied = _destructive(body, policy, trail, vercel_key)
    if isinstance(sheet_denied, Block):
        return _fail(trail, sheet_denied, data_dir)
    if isinstance(sheet_denied, Reject):
        return _notice(trail, sheet_denied.code, sheet_denied.control, PERMITTED, data_dir)

    book = read(data_dir / "budget.json")
    spent = book.get(trail.agent, Spend(0.0, 0))
    agent = policy.agents[trail.agent]
    if spent.usd >= agent.usd_cap:
        return _fail(trail, block("budget"), data_dir)

    denied = _jev_open(spans, policy, vercel_key, trail)
    if isinstance(denied, Block):
        if policy.level("prompt_injection") == "redact" and denied.code == "jev.block":
            return _notice(trail, denied.code, "prompt_injection", "[REDACTED]", data_dir)
        return _fail(trail, denied, data_dir)

    upstream = complete(body, openai_key)
    if isinstance(upstream, UpstreamErr):
        return _fail(trail, block("upstream.error"), data_dir)
    if upstream.status != 200:
        trail.decision = "allow"
        trail.check = "upstream"
        trail.status = upstream.status
        trail.payload = upstream.body
        return _write(trail, data_dir)

    out_spans = outbound_spans(upstream.body)
    _charge(trail, policy, upstream.body, out_spans, data_dir)
    tool_decision = _outbound_tools(upstream.body, agent.tools, policy)
    if isinstance(tool_decision, Block):
        return _fail(trail, tool_decision, data_dir)
    if isinstance(tool_decision, Reject):
        return _notice(trail, tool_decision.code, tool_decision.control, PERMITTED, data_dir)
    sheet_denied = _destructive(upstream.body, policy, trail, vercel_key, request=body)
    if isinstance(sheet_denied, Block):
        return _fail(trail, sheet_denied, data_dir)
    if isinstance(sheet_denied, Reject):
        return _notice(trail, sheet_denied.code, sheet_denied.control, PERMITTED, data_dir)
    pairs = [(span, scan_span(span, policy, signatures)) for span in out_spans]
    folded = fold([item for _span, item in pairs])
    if isinstance(folded, Block):
        return _fail(trail, folded, data_dir)
    if isinstance(folded, Reject):
        return _notice(trail, folded.code, folded.control, PERMITTED, data_dir)
    if isinstance(folded, Redact):
        _apply(upstream.body, folded)
        trail.mark(folded)

    denied = _jev_output(spans, pairs, policy, vercel_key, trail)
    if isinstance(denied, Block):
        if policy.level("prompt_injection") == "redact" and denied.code == "jev.block":
            return _notice(trail, denied.code, "prompt_injection", "[REDACTED]", data_dir)
        return _fail(trail, denied, data_dir)

    trail.status = 200
    trail.payload = upstream.body
    return _write(trail, data_dir)


def _destructive(
    body: dict[str, object],
    policy: Policy,
    trail: Trail,
    api_key: str,
    request: dict[str, object] | None = None,
) -> Block | Reject | None:
    if policy.level("dangerous_actions") == "disabled":
        return None
    context = request if request is not None else body
    text = action_text(inbound_spans(context) + outbound_spans(body))
    if text == "":
        return None
    hit = evaluate_destructive(text, api_key)
    trail.jev_latency_ms = (trail.jev_latency_ms or 0.0) + hit.latency_ms
    trail.seen(hit.confidence)
    if hit.block is None:
        return block("jev.destructive_error")
    trail.destructive = hit.block
    if not hit.block:
        if safe_enough(hit.confidence, policy.require_high_confidence):
            return None
        if policy.level("dangerous_actions") == "redact":
            return Reject("jev.action_confidence", "dangerous_actions")
        return block("jev.action_confidence")
    if policy.level("dangerous_actions") == "redact":
        return Reject("jev.destructive", "dangerous_actions")
    return block("jev.destructive")


def _scan(spans: list[Span], policy: Policy, signatures: tuple[Signature, ...]) -> Decision:
    return fold([scan_span(span, policy, signatures) for span in spans])


def _jev_open(spans: list[Span], policy: Policy, api_key: str, trail: Trail) -> Block | None:
    if policy.level("prompt_injection") == "disabled":
        return None
    if _answered(spans) and policy.level("dangerous_actions") != "disabled":
        return None
    text = injection_text(spans)
    if text == "":
        return None
    return _call(text, "request", policy, api_key, trail)


def _jev_output(
    inbound: list[Span],
    pairs: list[tuple[Span, Decision]],
    policy: Policy,
    api_key: str,
    trail: Trail,
) -> Block | None:
    if policy.level("prompt_injection") == "disabled":
        return None
    answer = _labeled(
        span
        for span, outcome in pairs
        if RULES[span.target].jev == "allow_only" and isinstance(outcome, Allow)
    )
    if answer == "":
        return None
    request = injection_text(inbound)
    text = f"{request}\n{answer}" if request else answer
    return _call(text, "output", policy, api_key, trail)


def _answered(spans: Iterable[Span]) -> bool:
    return any(span.target == "assistant" and span.text for span in spans)


def injection_text(spans: Iterable[Span]) -> str:
    return _labeled(span for span in spans if RULES[span.target].jev == "after_redact")


def action_text(spans: Iterable[Span]) -> str:
    action = _labeled(span for span in spans if span.target in ("tool_args", "assistant"))
    if action == "":
        return ""
    task = _labeled(span for span in spans if span.target == "prompt" and span.path[:1] == ("messages",))
    if task == "":
        return action
    return f"{task}\n{action}"


def _labeled(spans: Iterable[Span]) -> str:
    return "\n".join(f"[{span.target}]\n{span.text}" for span in spans if span.text)


def _call(text: str, direction: str, policy: Policy, api_key: str, trail: Trail) -> Block | None:
    hit = evaluate(text, direction, api_key)
    trail.note(hit)
    if hit.block is None:
        return block("jev.error")
    if hit.block:
        return judge(hit.block)
    if safe_enough(hit.confidence, policy.require_high_confidence):
        return None
    return block("jev.low_confidence")


def _charge(
    trail: Trail,
    policy: Policy,
    body: dict[str, object],
    spans: list[Span],
    data_dir: Path,
) -> None:
    assistant = "\n".join(span.text for span in spans if span.target == "output")
    tokens = _tokens(body, assistant)
    usd = tokens * policy.models[trail.model] / 1000
    path = data_dir / "budget.json"
    book = read(path)
    spent = book.get(trail.agent, Spend(0.0, 0))
    book[trail.agent] = Spend(spent.usd + usd, spent.tokens + tokens)
    write(path, book)
    trail.tokens = tokens
    trail.usd = usd


def _tokens(body: dict[str, object], assistant: str) -> int:
    usage = body.get("usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int) and not isinstance(total, bool):
            return total
    return len(assistant) // 4


def _gate(header: str | None, body: dict[str, object], policy: Policy) -> Block | Reject | None:
    if not header:
        return block("agent.missing")
    agent = policy.agents.get(header)
    if agent is None:
        return block("agent.unknown")
    if not agent.enabled:
        return block("agent.disabled")
    model = body.get("model")
    if not isinstance(model, str) or model not in policy.models:
        return block("model.unknown")
    mode = policy.level("tool_calls")
    if mode == "disabled":
        return None
    for name in invoked_tools(body):
        if name not in agent.tools:
            if mode == "redact":
                return Reject("tool.denied", "tool_calls")
            return block("tool.denied")
    return None


def _outbound_tools(body: dict[str, object], allowed: frozenset[str], policy: Policy) -> Block | Reject | None:
    mode = policy.level("tool_calls")
    if mode == "disabled":
        return None
    choices = body.get("choices")
    if not isinstance(choices, list):
        return None
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        calls = message.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            name = _function_name(call)
            if name is not None and name not in allowed:
                if mode == "redact":
                    return Reject("tool.denied", "tool_calls")
                return block("tool.denied")
    return None


def invoked_tools(body: dict[str, object]) -> list[str]:
    names: list[str] = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "tool" and isinstance(message.get("name"), str):
                names.append(message["name"])
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    name = _function_name(call)
                    if name is not None:
                        names.append(name)
    return names


def tool_names(body: dict[str, object]) -> list[str]:
    names: list[str] = []
    tools = body.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            name = _function_name(tool)
            if name is not None:
                names.append(name)
    messages = body.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "tool" and isinstance(message.get("name"), str):
                names.append(message["name"])
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    name = _function_name(call)
                    if name is not None:
                        names.append(name)
    return names


def inbound_spans(body: dict[str, object]) -> list[Span]:
    spans: list[Span] = []
    messages = body.get("messages")
    if isinstance(messages, list):
        for index, message in enumerate(messages):
            if isinstance(message, dict):
                _collect(spans, message, ("messages", index), True)
    tools = body.get("tools")
    if isinstance(tools, list):
        for index, tool in enumerate(tools):
            _tool_description(spans, tool, index)
    return spans


def outbound_spans(body: dict[str, object]) -> list[Span]:
    spans: list[Span] = []
    choices = body.get("choices")
    if isinstance(choices, list):
        for index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                _collect(spans, message, ("choices", index, "message"), False)
    return spans


def _collect(spans: list[Span], message: dict[str, object], prefix: tuple[str | int, ...], inbound: bool) -> None:
    content = message.get("content")
    if isinstance(content, str):
        target: Target = "prompt"
        if inbound and message.get("role") == "tool":
            target = "tool_result"
        elif inbound and message.get("role") == "assistant":
            target = "assistant"
        elif not inbound:
            target = "output"
        spans.append(Span(content, target, prefix + ("content",)))
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            path = prefix + ("tool_calls", index, "function", "arguments")
            spans.append(Span(arguments, "tool_args", path))


def _tool_description(spans: list[Span], tool: object, index: int) -> None:
    if not isinstance(tool, dict):
        return
    function = tool.get("function")
    if not isinstance(function, dict):
        return
    description = function.get("description")
    if isinstance(description, str) and description != "":
        spans.append(Span(description, "prompt", ("tools", index, "function", "description")))


def _function_name(node: object) -> str | None:
    if not isinstance(node, dict):
        return None
    function = node.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if isinstance(name, str):
        return name
    return None


def _apply(body: dict[str, object], outcome: Redact) -> None:
    for span in outcome.spans:
        _put(body, span.path, span.text)


def _rewritten(spans: list[Span], outcome: Redact) -> list[Span]:
    by_path = {span.path: span.text for span in outcome.spans}
    return [Span(by_path[span.path], span.target, span.path) if span.path in by_path else span for span in spans]


def _put(node: object, path: tuple[str | int, ...], value: str) -> None:
    key = path[0]
    if len(path) == 1:
        if isinstance(node, dict) and isinstance(key, str):
            node[key] = value
        elif isinstance(node, list) and isinstance(key, int):
            node[key] = value
        return
    child: object | None = None
    if isinstance(node, dict) and isinstance(key, str):
        child = node.get(key)
    elif isinstance(node, list) and isinstance(key, int):
        child = node[key]
    if child is not None:
        _put(child, path[1:], value)


def _fail(trail: Trail, item: Block, data_dir: Path) -> tuple[int, object]:
    trail.decision = "block"
    trail.reason = item.reason
    trail.check = item.check
    trail.control = control_of(item.code)
    trail.mode = "strict"
    trail.action = "terminate"
    trail.status = 403
    trail.payload = {"error": {"message": item.reason, "type": "control_layer", "code": item.code}}
    return _write(trail, data_dir)


def _notice(trail: Trail, code: str, control: str, message: str, data_dir: Path) -> tuple[int, object]:
    trail.decision = "redact"
    trail.reason = message
    trail.check = code
    trail.control = control
    trail.mode = "redact"
    trail.action = "reject" if control in ("tool_calls", "dangerous_actions") else "redact"
    trail.status = 200
    trail.payload = {
        "object": "chat.completion",
        "choices": [{"message": {"role": "assistant", "content": message}}],
    }
    return _write(trail, data_dir)


def _write(trail: Trail, data_dir: Path) -> tuple[int, object]:
    line: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": trail.agent,
        "model": trail.model,
        "tool": trail.tool,
        "decision": trail.decision,
        "reason": trail.reason,
        "check": trail.check,
        "control": trail.control,
        "mode": trail.mode,
        "action": trail.action,
        "continue": trail.status != 403,
        "tokens": trail.tokens,
        "usd": trail.usd,
        "latency_ms": int((time.perf_counter() - trail.started) * 1000),
        "jev_latency_ms": trail.jev_latency_ms,
    }
    if trail.request_id != "":
        line["request_id"] = trail.request_id
    if trail.sanitized:
        line["sanitized"] = trail.sanitized
    if trail.jev is not None:
        line["jev"] = trail.jev
    if trail.destructive is not None:
        line["destructive"] = trail.destructive
    if trail.confidence is not None:
        line["confidence"] = trail.confidence
        if isinstance(trail.payload, dict):
            trail.payload["confidence"] = trail.confidence
    append(data_dir / "audit.jsonl", line)
    return trail.status, trail.payload
