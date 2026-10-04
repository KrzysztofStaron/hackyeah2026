from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from control.controls import control_of, signature_control
from control.policy import Policy
from control.signatures import Signature

Target = Literal["prompt", "assistant", "tool_result", "tool_args", "output"]
JevMode = Literal["after_redact", "allow_only", "action"]

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
API_KEY = re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


@dataclass(frozen=True)
class TargetRule:
    checks: tuple[str, ...]
    jev: JevMode


RULES: dict[str, TargetRule] = {
    "prompt": TargetRule(("emails", "secrets", "signatures"), "after_redact"),
    "assistant": TargetRule(("emails", "secrets", "signatures"), "action"),
    "tool_result": TargetRule(("emails", "secrets", "signatures"), "after_redact"),
    "tool_args": TargetRule(("emails", "secrets", "signatures"), "after_redact"),
    "output": TargetRule(("emails", "secrets", "signatures"), "allow_only"),
}


@dataclass(frozen=True)
class Span:
    text: str
    target: Target
    path: tuple[str | int, ...]


@dataclass(frozen=True)
class Allow:
    pass


@dataclass(frozen=True)
class Block:
    code: str
    check: str
    reason: str


@dataclass(frozen=True)
class Redact:
    spans: tuple[Span, ...]
    checks: tuple[str, ...]


@dataclass(frozen=True)
class Reject:
    code: str
    control: str


Decision = Allow | Block | Redact | Reject


def block(code: str) -> Block:
    return Block(code, code, code)


def fold(outcomes: list[Decision]) -> Decision:
    spans: list[Span] = []
    checks: list[str] = []
    rejected: Reject | None = None
    blocks: list[Block] = []
    for outcome in outcomes:
        if isinstance(outcome, Block):
            blocks.append(outcome)
            continue
        if isinstance(outcome, Reject):
            rejected = outcome
        if isinstance(outcome, Redact):
            spans.extend(outcome.spans)
            checks.extend(outcome.checks)
    if blocks:
        return preferred_block(blocks)
    if rejected is not None:
        return rejected
    if spans:
        return Redact(tuple(spans), tuple(checks))
    return Allow()


def preferred_block(blocks: list[Block]) -> Block:
    order = ("dangerous_actions", "prompt_injection", "secrets", "tool_calls", "pii")

    def rank(item: Block) -> int:
        control = control_of(item.code)
        if control in order:
            return order.index(control)
        return len(order)

    return min(blocks, key=rank)


def scan_span(span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision:
    text = span.text
    checks: list[str] = []
    blocks: list[Block] = []
    for name in RULES[span.target].checks:
        current = Span(text, span.target, span.path)
        outcome = _run(name, current, policy, signatures)
        if isinstance(outcome, Block):
            blocks.append(outcome)
            continue
        if isinstance(outcome, Reject):
            if blocks:
                return preferred_block(blocks)
            return outcome
        if isinstance(outcome, Redact):
            text = outcome.spans[0].text
            checks.extend(outcome.checks)
    if blocks:
        return preferred_block(blocks)
    if checks:
        return Redact((Span(text, span.target, span.path),), tuple(checks))
    return Allow()


def _run(name: str, span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision | None:
    if name == "emails":
        return _pattern(policy.level("pii"), "emails", EMAIL, span)
    if name == "secrets":
        return _secret(span, policy)
    if name == "signatures":
        return _signatures(span, policy, signatures)
    return None


def _pattern(mode: str, code: str, pattern: re.Pattern[str], span: Span) -> Decision | None:
    if mode == "disabled" or pattern.search(span.text) is None:
        return None
    if mode == "strict":
        return block(code)
    return _redacted(code, pattern.sub("[REDACTED]", span.text), span)


def _secret(span: Span, policy: Policy) -> Decision | None:
    mode = policy.level("secrets")
    if mode == "disabled":
        return None
    if API_KEY.search(span.text) is None and PRIVATE_KEY.search(span.text) is None:
        return None
    if mode == "strict":
        return block("secrets")
    text = PRIVATE_KEY.sub("[REDACTED]", API_KEY.sub("[REDACTED]", span.text))
    return _redacted("secrets", text, span)


def _redacted(code: str, text: str, span: Span) -> Redact:
    return Redact((Span(text, span.target, span.path),), (code,))


def _signatures(span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision | None:
    text = span.text
    checks: list[str] = []
    blocks: list[Block] = []
    for row in signatures:
        control = signature_control(row.id)
        mode = policy.level(control)
        if mode == "disabled" or span.target not in row.targets:
            continue
        current = Span(text, span.target, span.path)
        code = f"signatures.{row.id}"
        matched = row.id == "model_host" and _untrusted_host(current.text, row.pattern, policy.trusted_hosts)
        if row.id != "model_host":
            matched = row.pattern.search(current.text) is not None
        if not matched:
            continue
        if mode == "strict" or row.action == "block":
            if mode == "strict" or control == "dangerous_actions":
                blocks.append(block(code))
                continue
        if control == "dangerous_actions" and span.target == "tool_args":
            return Reject(code, control)
        if row.id == "model_host":
            text = _redact_hosts(current.text, row.pattern, policy.trusted_hosts)
        else:
            text = row.pattern.sub(row.replace, current.text)
        checks.append(code)
    if blocks:
        return preferred_block(blocks)
    if not checks:
        return None
    return Redact((Span(text, span.target, span.path),), tuple(checks))


def _redact_hosts(text: str, pattern: re.Pattern[str], trusted: frozenset[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        host = urlparse(match.group(0)).hostname
        if host and host not in trusted:
            return "[REDACTED]"
        return match.group(0)

    return pattern.sub(replace, text)


def _untrusted_host(text: str, pattern: re.Pattern[str], trusted: frozenset[str]) -> bool:
    for match in pattern.finditer(text):
        host = urlparse(match.group(0)).hostname
        if host and host not in trusted:
            return True
    return False
