# AI Control Layer

The brief is the checklist. This file is the smallest build that covers it.

The layer sits on `POST /v1/chat/completions`. A developer changes `base_url`. The proxy protects data, applies guardrails, caps spend, and blocks exploits. Deterministic checks run first. Jev runs only when those checks did not already decide. One policy catalog holds the rules. Judges can edit that catalog and the signature file, and the next request changes.

Agent calls go to OpenAI. Jev goes to the Vercel AI Gateway. There is no local model and no Ollama path.

Grading in the criteria PDF is guardrails 30%, architecture and performance 20%, reporting 20%, tests 15%, implementability 15%. The rules PDF swaps the last two to 20% and 10%. Each control gets an allow case and a block or redact case.

## Integration

The same request carries the prompt, tool calls, and later tool results. Tool calls are how MCP shows up. There is no second endpoint and no SDK.

Commercial calls forward to `https://api.openai.com/v1` with `OPENAI_APIKEY` from `.env.local`. The agent never sees that key. Allowed models are OpenAI model ids from the policy. Anything else is blocked.

Jev is `POST https://ai-gateway.vercel.sh/v1/evaluate`, model `typesafe-ai/jev`, `Authorization: Bearer` plus `VERCEL_APIKEY`. One `boolean` question asks it to choose block or allow. We read `answers.block.answer`. `true` blocks. `false` allows. A missing answer blocks. `state` is a JSON object. No AI SDK, TanStack, LangChain, Cloudflare, eve, or TypeSafe client.

`.env.local` is gitignored. Both keys are required. There is no mock.

`policy.yaml` and `signatures.json` are re-read on every request. A file that does not parse is rejected and the last valid copy stays active.

## Pipeline

Stop on the first block.

1. Policy. The agent id is in the file and enabled. The model is on the allowlist. The tool name is on that agent's list.
2. Data. Email and an API-key or private-key pattern, on the way in and on the model output and tool results. Action is `redact` or `block`, set in the policy.
3. Exploits. `signatures.json` is the externally managed feed. Each row has an id, a regex, where it applies (`prompt`, `tool_args`, `tool_result`), and an action. Starter rows are code execution in tool arguments, pickle or `.pkl` loads, a model download from a host not on the trusted list, and `ignore previous instructions`.
4. Jev, only if nothing above already blocked. One evaluate call sees the prompt, tool arguments, and tool results together, each labeled. On the way out, the same request is included with the model answer. Jev chooses block or allow. Block stops the request. A missing choice, an error, or a timeout blocks.
5. Budget. `tokens × usd_per_1k` for that OpenAI model, added to the agent's USD spend. Over the cap, block. A runaway loop burns the same cap.
6. Forward to OpenAI. Run steps 2 and 3 on the way out.
7. Append one audit record, including total latency and Jev latency when Jev ran.

## Policy

`policy.yaml` is the only catalog. It holds agent ids, the tool allowlist, the OpenAI model allowlist with `usd_per_1k`, the USD cap, the on/off switch and action for each check, and the trusted hosts.

Two documented files show strictness. `standard.yaml` and `strict.yaml`. The difference is whether a data match redacts or blocks. Comments in the files say which is which. Budget rules are in both.

## Reporting

One JSONL audit file. Each line has time, agent, model or tool, decision, reason, which check matched, tokens, USD, and latency. Matched secret or PII text is stored redacted. `GET /v1/audit/export` returns that file.

One page reads `GET /v1/report` on a short poll. It shows which controls are on, the active policy and when it loaded, blocked and redacted counts, USD and tokens per agent, and the latest events. That is the dashboard. Management reads the totals. A security team reads the events and the export.

## Tests

`pytest` calls the real proxy with the keys in `.env.local`. There is no mock. Judges run this suite. It includes budget limits and exploit cases.

Each control has one allowed case and one blocked or redacted case.

- Known agent, allowlisted model, allowlisted tool.
- Unknown agent, unknown model, tool not on the list.
- Email and a secret, redacted or blocked per the active policy. Clean text, unchanged.
- Each starter signature, blocked. A benign string, allowed.
- A Jev choice of block, blocked. A Jev choice of allow, allowed.
- Spend over the USD cap, blocked. Spend under the cap, allowed.
- Editing the policy or adding a signature changes the next request.

## README

A Mermaid diagram of the pipeline. A table mapping each check to an OWASP Top 10 for LLM Applications id. The license names of the dependencies. How to point an agent at the proxy, edit the two files, open the page, and run `pytest`.

## Done

A normal request reaches OpenAI and shows on the page. A secret or email in the output is caught. A signature match is blocked, including a row added after startup. Jev scores whatever the cheap checks did not decide, through the Gateway. The USD cap blocks the next request when it is spent. `pytest` shows an allow and a block or redact for every control above.
