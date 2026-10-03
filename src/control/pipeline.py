from __future__ import annotations

import time
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
    Span,
    Target,
    block,
    fold,
    scan_span,
)
from control.jev import JevHit, evaluate, judge
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
    jev: dict[str, float] | None = None

    def note(self, hit: JevHit) -> None:
        if self.jev is None:
            self.jev = {}
            self.jev_latency_ms = 0.0
        self.jev_latency_ms = (self.jev_latency_ms or 0.0) + hit.latency_ms
        if hit.probabilities is None:
            return
        for name, probability in hit.probabilities.items():
            self.jev[name] = max(self.jev.get(name, probability), probability)

    def mark(self, outcome: Redact) -> None:
        names = [part for part in self.check.split(",") if part]
        for name in outcome.checks:
            if name not in names:
                names.append(name)
        self.decision = "redact"
        self.check = ",".join(names)
        self.reason = self.check
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
    if denied is not None:
        return _fail(trail, denied, data_dir)

    spans = inbound_spans(body)
    inbound = _scan(spans, policy, signatures)
    if isinstance(inbound, Block):
        return _fail(trail, inbound, data_dir)
    if isinstance(inbound, Redact):
        _apply(body, inbound)
        trail.mark(inbound)
        spans = _rewritten(spans, inbound)

    denied = _jev_open(spans, policy, vercel_key, trail)
    if denied is not None:
        return _fail(trail, denied, data_dir)

    book = read(data_dir / "budget.json")
    spent = book.get(trail.agent, Spend(0.0, 0))
    agent = policy.agents[trail.agent]
    if agent.call_cap is not None and spent.calls >= agent.call_cap:
        return _fail(trail, block("budget"), data_dir)
    if spent.usd >= agent.usd_cap:
        return _fail(trail, block("budget"), data_dir)

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
    pairs = [(span, scan_span(span, policy, signatures)) for span in out_spans]
    folded = fold([item for _span, item in pairs])
    if isinstance(folded, Block):
        return _fail(trail, folded, data_dir)
    if isinstance(folded, Redact):
        _apply(upstream.body, folded)
        trail.mark(folded)

    denied = _jev_output(pairs, policy, vercel_key, trail)
    if denied is not None:
        return _fail(trail, denied, data_dir)

    trail.status = 200
    trail.payload = upstream.body
    return _write(trail, data_dir)


def _scan(spans: list[Span], policy: Policy, signatures: tuple[Signature, ...]) -> Decision:
    return fold([scan_span(span, policy, signatures) for span in spans])


def _jev_open(spans: list[Span], policy: Policy, api_key: str, trail: Trail) -> Block | None:
    if not policy.jev.enabled:
        return None
    prompts = [
        span.text
        for span in spans
        if span.target == "prompt" and RULES[span.target].jev == "after_redact" and span.text
    ]
    results = [
        span.text
        for span in spans
        if span.target == "tool_result" and RULES[span.target].jev == "after_redact" and span.text
    ]
    if prompts:
        denied = _call("\n".join(prompts), "prompt", policy, api_key, trail)
        if denied is not None:
            return denied
    for text in results:
        denied = _call(text, "tool_result", policy, api_key, trail)
        if denied is not None:
            return denied
    return None


def _jev_output(
    pairs: list[tuple[Span, Decision]],
    policy: Policy,
    api_key: str,
    trail: Trail,
) -> Block | None:
    if not policy.jev.enabled:
        return None
    parts = [
        span.text
        for span, outcome in pairs
        if RULES[span.target].jev == "allow_only" and isinstance(outcome, Allow) and span.text
    ]
    if not parts:
        return None
    return _call("\n".join(parts), "output", policy, api_key, trail)


def _call(text: str, direction: str, policy: Policy, api_key: str, trail: Trail) -> Block | None:
    hit = evaluate(text, direction, api_key)
    trail.note(hit)
    if hit.probabilities is None:
        return block("jev.error")
    return judge(hit.probabilities, policy.jev.action, policy.jev.thresholds)


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
    book[trail.agent] = Spend(spent.usd + usd, spent.tokens + tokens, spent.calls + 1)
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


def _gate(header: str | None, body: dict[str, object], policy: Policy) -> Block | None:
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
    for name in tool_names(body):
        if name not in agent.tools:
            return block("tool.denied")
    return None


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
        if not inbound:
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
    trail.status = 403
    trail.payload = {"error": {"message": item.reason, "type": "control_layer", "code": item.code}}
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
    append(data_dir / "audit.jsonl", line)
    return trail.status, trail.payload
