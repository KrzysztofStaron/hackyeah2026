---
name: connect-control-layer
description: Routes an AI agent's LLM traffic through the taski AI Control Layer proxy so every prompt, tool call, and tool result is checked for PII, secrets, prompt injection, dangerous actions, and budget. Use when wiring an agent, chatbot, or OpenAI-compatible client to the control layer, changing its base_url to the proxy, registering a new agent id in policy.yaml, or handling the proxy's 403 blocks and redacted responses.
---

# Connect an agent to the control layer

The proxy is a drop-in replacement for OpenAI's `POST /v1/chat/completions`. The agent keeps its own client and its own tool loop. Only the base URL and one header change.

## Checklist

```
- [ ] 1. Register the agent id, model, and tools in the policy
- [ ] 2. Point the client at the proxy and send X-Agent-Id
- [ ] 3. Turn streaming off
- [ ] 4. Send the full tool history on every turn
- [ ] 5. Handle 403 blocks and 200 refusals in the agent loop
- [ ] 6. Verify with one allowed and one blocked request
```

## 1. Register the agent in the policy

The proxy rejects any agent, model, or tool that the policy does not list. Add the agent to the active policy file (`POLICY_PATH`, default `policy/standard.yaml`):

```yaml
agents:
  my-agent:
    enabled: true
    usd_cap: 1.0
    tools:
    - lookup_customer
    - run_sql
models:
  gpt-4o-mini:
    usd_per_1k: 0.00015
```

- `tools` must contain the exact function names the agent declares. A call to any other tool is refused.
- `models` must contain the exact model id the agent sends. Any other model is blocked before it costs anything.
- The file is re-read on every request. No restart is needed. If the file fails to parse, the last valid copy stays active, so check the YAML before saving.

## 2. Point the client at the proxy

| Setting | Value |
|---|---|
| Base URL, local | `http://127.0.0.1:8000/v1` (start with `make run`) |
| Base URL, deployed | `https://taski-plum.vercel.app/v1` |
| Header `X-Agent-Id` | Required. The agent id from the policy |
| Header `X-Request-Id` | Optional. Copied into the audit line so a turn can be found later |
| API key | Any non-empty string. The proxy uses its own OpenAI key and the agent never sees it |

Python (`openai`):

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="unused",
    default_headers={"X-Agent-Id": "my-agent"},
)
```

TypeScript (`openai`):

```ts
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:8000/v1",
  apiKey: "unused",
  defaultHeaders: { "X-Agent-Id": "my-agent" },
});
```

Frameworks built on the OpenAI client (LangChain `ChatOpenAI`, LlamaIndex, Vercel AI SDK OpenAI provider, and similar) take the same two settings: a base URL and default headers. Set both there instead of patching the framework.

## 3. Turn streaming off

The proxy has to see the whole answer before it can scan it, so it always calls the model with `stream: false` and returns one JSON response. A client that asks for `stream: true` will get a body it cannot parse as a stream. Use the non-streaming call.

## 4. Send the full tool history on every turn

Each turn of the agent loop is one request to the proxy. Keep the standard OpenAI message format:

1. Send the conversation plus the `tools` declarations.
2. If the answer contains `tool_calls`, run them, then append the assistant message with its `tool_calls` and one `role: "tool"` message per result.
3. Send the next request with that history.

Tool results are checked like prompts. PII in a tool result reaches the model as `[REDACTED]`, and an injected instruction inside a tool result can stop the turn. This is why tool results must go back through the proxy, never straight to the model.

## 5. Handle the proxy's responses

The proxy returns one of three shapes. The agent loop must tell them apart.

**Allowed or redacted.** HTTP 200 with a normal chat completion. Redacted values appear as the literal string `[REDACTED]`. Use them as they are. Don't try to recover the original value, and don't ask the user for it.

**Refused, agent may continue.** HTTP 200 with a minimal completion that only has `choices[0].message.content`. Fields such as `id`, `usage`, and `finish_reason` may be missing, so read them as optional. The content is one of:

- `This action is not permitted by the current policy.` The tool call was dropped. Do not run it and do not retry it under another name.
- `[REDACTED]` A prompt injection was stripped.

Treat this as the model's reply for the turn and let the agent tell the user it couldn't do that action.

**Blocked, agent must stop.** HTTP 403:

```json
{ "error": { "message": "signatures.sql_danger", "type": "control_layer", "code": "signatures.sql_danger" } }
```

Stop the loop. Don't retry the same request, and don't rephrase it to get past the check. `error.message` is the same machine code as `error.code`, so map the code to your own sentence before showing it to a user. Branch on `error.code`:

| `error.code` | Meaning | What to fix |
|---|---|---|
| `agent.missing`, `agent.unknown`, `agent.disabled` | Header absent, id not in the policy, or disabled | Send `X-Agent-Id`, or register the agent |
| `model.unknown` | Model not in `models` | Use a listed model, or add it with a price |
| `tool.denied` | Tool not on this agent's list | Add the tool to the policy, if it should be allowed |
| `budget` | Agent's spend reached `usd_cap` | Raise the cap or wait for a reset |
| `secrets`, `signatures.*` | A secret or a known attack pattern matched | Not a wiring bug. The request was dangerous |
| `jev.*` | The AI judge flagged injection or a destructive action | Not a wiring bug |
| `policy.invalid` | The policy or signature file has never parsed | Fix the YAML or JSON |
| `upstream.error` | The proxy couldn't reach OpenAI | Retry later |

Only `upstream.error` is worth retrying, and only with backoff.

Python sketch of the loop's response handling:

```python
import httpx

response = httpx.post(
    f"{BASE_URL}/chat/completions",
    headers={"X-Agent-Id": "my-agent"},
    json={"model": "gpt-4o-mini", "messages": messages, "tools": tools},
    timeout=90,
)
payload = response.json()
if response.status_code == 403:
    return StopTurn(code=payload["error"]["code"], message=payload["error"]["message"])
message = payload["choices"][0]["message"]
calls = message.get("tool_calls") or []
```

With the `openai` SDK, a 403 raises `openai.PermissionDeniedError`. Read `error.body["error"]["code"]` from it and stop the loop.

## 6. Verify the connection

Run both against the proxy. The first must succeed. The second must come back as a 403 with code `signatures.sql_danger`, as long as `run_sql` is in the agent's tool list and `dangerous_actions` is `strict` (the default). With `dangerous_actions: redact` it comes back as a 200 refusal instead:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-Agent-Id: my-agent" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Say hello."}]}'

curl -s -w '\n%{http_code}\n' http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-Agent-Id: my-agent" \
  -d '{"model":"gpt-4o-mini","messages":[
        {"role":"user","content":"Clean up the invoices."},
        {"role":"assistant","content":null,"tool_calls":[{"id":"c1","type":"function",
          "function":{"name":"run_sql","arguments":"{\"query\":\"DROP TABLE invoices\"}"}}]},
        {"role":"tool","tool_call_id":"c1","name":"run_sql","content":"ok"}]}'
```

Then open the dashboard at `/` (or read `GET /v1/report`). Both requests should be in the audit log under the new agent id.

## Common mistakes

- Calling `api.openai.com` directly for some requests, such as summaries or retries. Every model call has to go through the proxy, or that call isn't checked or charged.
- Sending tool results to the model outside the proxy. The injection and PII checks on tool results are skipped.
- Retrying a 403 in a loop. Each attempt is a new audit line and still blocked.
- Declaring tools in code that aren't in the policy. The first call to them is refused.
