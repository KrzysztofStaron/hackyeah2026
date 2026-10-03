# AI Control Layer — cut requirements

HackYeah 2026, Goldman Sachs. Submission in English.

Source of truth, in this order:

1. `Partner Task [Goldman Sachs] - AI Control Layer` criteria PDF (the task).
2. `Terms and conditions of the "AI CONTROL LAYER" Competition` (the rules).

The previous spec is not a source of truth. If a line below is not in those two documents, it is a build choice and it is marked as one.

## Conflicts inside the source

Grading weights do not match.

| Criterion | Criteria PDF | Rules PDF |
| --- | --- | --- |
| Robustness and quality of guardrails | 30% | 30% |
| Architecture and performance | 20% | 20% |
| Security reporting | 20% | 20% |
| Self-testing suite | 15% | **20%** |
| Implementability and scalability | 15% | **10%** |

Plan as if tests are 20% and the SDK/scale story is 10%. A smaller set of controls, each with an allow case and a block case, scores higher than a wide set we only half-test.

Deadlines do not match either. The rules say work starts no earlier than 23:00 on 3 Oct and the submission is due 23:00 on 4 Oct. This doc previously said a 20:00 checkpoint and an 11:00 Sunday deadline. Confirm which clock the team is on before treating 20:00 as real.

## What the brief actually requires

- One control layer: a gateway, a proxy, a middleware, **or** an SDK. Not all of them.
- It inspects interactions and can block or redact. A human approval step is not required.
- One config source: controls, block-vs-redact thresholds, allowed models, resource or financial budgets.
- Deterministic checks. The brief's examples are PII, secrets, and access control.
- A semantic check, using a model where we can.
- Budgets. The brief's examples are resource access, compute time, **or** token spend, and it says to think about commercial APIs **and** local models.
- Historical attacks, fed from something outside the code. The brief names three: malicious code execution, unsafe deserialization, supply-chain attacks on model repos.
- A simple dashboard: controls, posture, blocked threats, consumption or cost. Exportable audit log.
- A test suite the judges run, with allowed and blocked cases, including budgets and exploits. It must run without our API keys.
- Judges may edit the config and the signature feed live and expect the next request to change. They may send ad-hoc prompts. They may look at latency numbers.
- A simple architecture diagram.
- Open-source dependencies only, licenses checked.
- The demo agent is not graded.

OWASP is an example of a source to read ("e.g. OWASP"), not a requirement to ship a coverage product.

## Build this

One OpenAI-compatible proxy. An agent points `base_url` at it. The same request path checks the incoming prompt, the tool calls inside the completion, and later tool results (that is where indirect injection shows up). No second product surface.

Pipeline, in order, stop on block:

1. Policy (who, which model, which tool).
2. Deterministic checks (PII, secrets, size, allowlists).
3. Signature file.
4. Jev, only if nothing above already blocked.
5. Budget.
6. Forward, then run the same deterministic and signature checks on the way out.

### Policy — `policy.yaml`, re-read every request

- Per control: on/off, and action `block` or `redact`, plus a confidence threshold for Jev.
- Allowed model names. Anything else is blocked.
- Agent id and the tools that agent may call.
- Token budget per agent (hard limit blocks). A price per 1k tokens in the same file turns that into a dollar figure for the dashboard. A local model is a row with price `0` (or its own token cap). That is the commercial-and-local requirement.
- Two strictness levels, `standard` and `strict`, as two small files or one switch. The brief asks for different levels. A third "permissive" file does not.
- Invalid YAML is rejected and the last good policy stays loaded.
- `enabled: false` on an agent, or globally, is the kill switch. No button.

### Deterministic

- PII: email, PESEL, credit card (Luhn). Same checks on the model output and on tool results.
- Secrets: one private-key pattern and one API-key pattern.
- Requests need an agent id that exists in the policy.
- Tool name must be on that agent's list.
- Prompt and tool-argument size cap.

### Semantic

Jev has no built-in safety taxonomy. We send an enum, it returns one of our labels plus a confidence. The labels in the old spec (`prompt_injection`, `jailbreak`, `data_exfiltration`, `irreversible_action`, `off_task`, `harmful_content`, `safe`) were invented.

Use four labels:

- `prompt_injection` (covers jailbreak text and instructions hidden in a tool result)
- `data_exfiltration`
- `off_task`
- `safe`

Policy maps label + threshold to block or redact. Default when Jev errors or times out: block.

Provider interface so tests never call the network:

- `jev` when `TYPESAFE_API_KEY` is set (the demo)
- `mock` otherwise (pytest)

Do not add OpenAI, Anthropic, or Ollama as extra classifiers. Ollama matters as an **upstream** model the proxy can forward to, which is the same OpenAI-compatible client.

Log the label, confidence, and Jev latency on the audit row. The dashboard line is "Jev / injection / 180 ms" only when Jev actually ran.

Pydantic's own note: Jev treats text as data, and injected text can move its answer. Regex and signatures run first for that reason. Do not claim Jev is the whole defense.

### Signatures — `signatures.json`, re-read every request

Each row: id, regex, where it applies (`prompt`, `tool_args`, `tool_result`), action, and an OWASP id string.

Starter rows, only what the brief names, plus the jailbreak string judges will type:

- code execution in tool arguments (`eval`, `exec`, `os.system`, `subprocess`, `curl | sh`)
- pickle / `.pkl` load
- model download from a host that is not on a trusted-host list in the policy
- `ignore previous instructions`

No URL fetcher. The file is the external feed. A judge adds a row, the next request hits it.

### Audit and dashboard

SQLite. Each row: time, agent, model or tool, decision, reason, which check matched, tokens, Jev label and latency if it ran. Store matched text redacted.

- `GET /v1/audit/export` returns JSON.
- One page: controls on or off, policy version and load time, blocked and redacted counts, token and dollar usage per agent, last events.

OWASP: a table in the README that maps each check to a 2025 LLM Top 10 id. Not a dashboard view.

### Tests

`make test` runs pytest with no API key and no network.

For every check we ship: one allowed case, one blocked or redacted case. Plus: budget exhaustion blocks, one test per starter signature, one indirect-injection case through the mock, one test that editing the policy changes the next decision.

Pytest's own summary is the report.

### Also ship

- Mermaid diagram in the README.
- `make run` starts the proxy and the dashboard.
- README: setup, how to point an agent at the proxy, how to edit policy and signatures, how to run tests.
- A short license list for dependencies.
- A tiny demo script with two mock tools, only so the pitch has something to click. It is not a requirement and it is not graded.

### Pitch sequence

1. Normal request, allowed, shows up on the dashboard.
2. PESEL in the output, redacted.
3. Tool result hides "ignore previous instructions", blocked (signature or mock; Jev on the live demo).
4. Tool not on the allowlist, blocked.
5. Repeated identical tool call hits the loop cap, blocked.
6. Judge edits `policy.yaml`, next request changes.
7. Judge adds a signature, next request changes.
8. `make test`.

Loop cap is one integer in the policy: the same tool name and the same arguments N times in a row blocks. The intro calls out runaway loops. This is the whole feature.

## Cut

| Old id | Decision | Why |
| --- | --- | --- |
| R-ARCH-2 separate `POST /v1/tool-check` | Cut | One proxy sees prompts, tool calls, and tool results. A second endpoint is a second product. |
| R-ARCH-3 SDK wrapper | Cut | The brief says proxy **or** SDK. Rules weight implementability at 10%. |
| R-ARCH-5 Anthropic, plus a classifier matrix | Cut | One OpenAI-compatible upstream covers hosted APIs and Ollama. |
| R-ARCH-6 exported PNG | Cut | Mermaid in the README is the diagram. |
| R-ARCH-7 five-tool demo agent | Cut | Agents are not graded. Two mock tools if we need a click path. |
| R-POL-3 per-agent model lists and reroute | Cut | One allowlist. Unknown models are blocked, not silently rerouted. |
| R-POL-4 argument constraints (payment cap, email domains, paths) | Cut | Tool allowlist is the access control. Extra constraint types are a policy language. |
| R-POL-8 `permissive.yaml` | Cut | Two levels satisfy "different strictness". |
| R-DET-1 phone, IBAN, IP | Cut | Email, PESEL, and card cover the PII example. More patterns mean more false positives, which the 30% criterion punishes. |
| R-DET-2 Slack, JWT, AWS, GitHub, connection strings | Cut | One key pattern and one private-key pattern. |
| R-DET-8 human approval for payments and email | Cut | The brief says inspect, redact, or block. An approval queue is a workflow. |
| R-SEM-2 seven labels | Replace | Jev does not emit these. We define four. |
| R-SEM-3 Jev on every tool call | Cut | Allowlist and signatures decide tool calls. Jev runs on text that survived the cheap checks. |
| R-SEM-5 openai / ollama classifiers | Cut | `jev` and `mock` only. |
| R-SEM-6 fail-open mode | Cut | Fail closed. No switch. |
| R-BUD-1 session and daily budgets | Cut | One token counter per agent. |
| R-BUD-3 compute-seconds accounting | Cut | Local models are a price row (0) or a token cap in the same counter. |
| R-BUD-4 requests-per-minute | Cut | Not in the brief. The token cap already stops a loop from spending. |
| R-BUD-6 soft warning | Cut | Hard block only. |
| R-BUD-7 dashboard kill button | Cut | `enabled: false` in the policy, picked up on the next request. |
| R-SIG-1 URL feed and refetch interval | Cut | Judges edit a file. A file watcher is the feed. |
| R-SIG-3 path traversal and SSRF | Cut | Not the three attacks the brief names. |
| R-OWASP-2 coverage dashboard | Cut | README table. Tags stay on signature rows because they are free. |
| R-REP-2 CSV export | Cut | JSON is exportable. |
| R-REP-3 cost-over-time chart, top-threats ranking | Cut | Counts, last events, budget numbers. |
| R-REP-4 filters and full stage-trace UI | Cut | One list. The row already says which check fired. |
| R-REP-6 approvals screen | Cut | No approval feature. |
| R-REP-7 kill button | Cut | Same as the policy flag. |
| R-REP-8 p50/p95 per stage, throughput, `GET /metrics` | Cut | One latency number per request, including Jev when it ran. Enough for "produce telemetry". |
| R-REP-9 SSE or websocket | Cut | The page polls. |
| R-TEST-6 HTML report grouped by OWASP | Cut | Pytest summary. |
| R-TEST-7 standalone benchmark | Cut | Latency is already on each audit row. |
| R-TEST-8 red-team prompt pack as a deliverable | Cut | The tests are the pack. |
| R-NF-1 p95 under 10 ms | Cut | Do not promise a number. Cheap checks first is the design. |
| R-NF-3 Redis, horizontal scale | Cut | Say in the README that SQLite is the demo store. Do not build Redis. |

## Explicitly still in, because the brief or the judges force it

- Hot reload of policy and signatures. Judges will edit both.
- Output filtering, not only input. The intro calls out sensitive data on the way out.
- Allowed models in the policy.
- A dollar view, even if it is `tokens × price` with a local price of 0.
- The three named historical attacks, as data in a file, not as code.
- Tests with no keys. Judges run them on their machine.
- Mock classifier. Their machine has no Jev key.
