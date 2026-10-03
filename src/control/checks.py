from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from control.policy import Policy
from control.signatures import Signature

Target = Literal["prompt", "tool_result", "tool_args", "output"]
JevMode = Literal["after_redact", "allow_only", "never"]

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
API_KEY = re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


@dataclass(frozen=True)
class TargetRule:
    checks: tuple[str, ...]
    jev: JevMode


RULES: dict[str, TargetRule] = {
    "prompt": TargetRule(("data_email", "data_secret", "signatures"), "after_redact"),
    "tool_result": TargetRule(("data_email", "data_secret", "signatures"), "after_redact"),
    "tool_args": TargetRule(("data_email", "data_secret", "signatures"), "never"),
    "output": TargetRule(("data_email", "data_secret", "signatures"), "allow_only"),
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


Decision = Allow | Block | Redact


def block(code: str) -> Block:
    return Block(code, code, code)


def fold(outcomes: list[Decision]) -> Decision:
    spans: list[Span] = []
    checks: list[str] = []
    for outcome in outcomes:
        if isinstance(outcome, Block):
            return outcome
        if isinstance(outcome, Redact):
            spans.extend(outcome.spans)
            checks.extend(outcome.checks)
    if spans:
        return Redact(tuple(spans), tuple(checks))
    return Allow()


def scan_span(span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision:
    text = span.text
    checks: list[str] = []
    for name in RULES[span.target].checks:
        current = Span(text, span.target, span.path)
        outcome = _run(name, current, policy, signatures)
        if isinstance(outcome, Block):
            return outcome
        if isinstance(outcome, Redact):
            text = outcome.spans[0].text
            checks.extend(outcome.checks)
    if checks:
        return Redact((Span(text, span.target, span.path),), tuple(checks))
    return Allow()


def _run(name: str, span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision | None:
    if name == "data_email":
        return _pattern(policy.data_email.enabled, policy.data_email.action, "data_email", EMAIL, span)
    if name == "data_secret":
        return _secret(span, policy)
    if name == "signatures":
        return _signatures(span, policy, signatures)
    return None


def _pattern(enabled: bool, action: str, code: str, pattern: re.Pattern[str], span: Span) -> Decision | None:
    if not enabled or pattern.search(span.text) is None:
        return None
    if action == "block":
        return block(code)
    return _redacted(code, pattern.sub("[REDACTED]", span.text), span)


def _secret(span: Span, policy: Policy) -> Decision | None:
    if not policy.data_secret.enabled:
        return None
    if API_KEY.search(span.text) is None and PRIVATE_KEY.search(span.text) is None:
        return None
    if policy.data_secret.action == "block":
        return block("data_secret")
    text = PRIVATE_KEY.sub("[REDACTED]", API_KEY.sub("[REDACTED]", span.text))
    return _redacted("data_secret", text, span)


def _redacted(code: str, text: str, span: Span) -> Redact:
    return Redact((Span(text, span.target, span.path),), (code,))


def _signatures(span: Span, policy: Policy, signatures: tuple[Signature, ...]) -> Decision | None:
    if not policy.signatures_enabled:
        return None
    text = span.text
    checks: list[str] = []
    for row in signatures:
        if span.target not in row.targets:
            continue
        current = Span(text, span.target, span.path)
        code = f"signatures.{row.id}"
        if row.id == "model_host":
            if not _untrusted_host(current.text, row.pattern, policy.trusted_hosts):
                continue
            if row.action == "block":
                return block(code)
            text = _redact_hosts(current.text, row.pattern, policy.trusted_hosts)
        else:
            if row.pattern.search(current.text) is None:
                continue
            if row.action == "block":
                return block(code)
            text = row.pattern.sub(row.replace, current.text)
        checks.append(code)
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
