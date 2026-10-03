# Control layer

The proxy sits on `POST /v1/chat/completions`. Point an agent at it by changing `base_url`. The agent keeps its own client. The proxy checks the request, calls Jev when the cheap checks did not already decide, forwards the call to OpenAI, and writes an audit line.

## Run the proxy

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
make run
```

`make run` starts uvicorn for `src/control/app.py` on `127.0.0.1:8000`.

Set `base_url` to `http://127.0.0.1:8000/v1`.

Send the header `X-Agent-Id`. `policy/standard.yaml` allows the agent id `demo` with model `gpt-4o-mini`.

The process reads `OPENAI_APIKEY` and `VERCEL_APIKEY` from `.env.local` when those variables are missing from the environment.

Open the report page at `/`.

## Edit the catalog

`POLICY_PATH` defaults to `policy/standard.yaml`.

`SIGNATURES_PATH` defaults to `signatures.json`.

`DATA_DIR` defaults to `data`.

`policy/standard.yaml` redacts an email and blocks a secret. Its Jev thresholds are 0.8.

`policy/strict.yaml` blocks an email. Its Jev thresholds are 0.6.

Each request reads both files again. A file that fails to parse keeps the last successful parse of that path. Spend is stored in `data/budget.json`. The audit log is `data/audit.jsonl`.

## Run the tests

```bash
make test
```

`make test` runs `pytest` against the real OpenAI API and the real Vercel AI Gateway. The suite reads the keys from `.env.local`.

## Pipeline

```mermaid
flowchart TD
  request[Chat request] --> refresh[Refresh policy and signatures]
  refresh --> gate[Check agent, model, and tools]
  gate --> inbound[Scan inbound spans]
  inbound --> jevIn[Jev on prompt and tool results]
  jevIn --> cap[Check the USD cap]
  cap --> openai[Forward to OpenAI]
  openai --> charge[Add token cost]
  charge --> outbound[Scan output spans]
  outbound --> jevOut[Jev on assistant text left as Allow]
  jevOut --> audit[Append one audit line]
  gate --> blocked[Return 403]
  inbound --> blocked
  jevIn --> blocked
  cap --> blocked
  outbound --> blocked
  jevOut --> blocked
```

A block stops the request. The output scan still records the OpenAI token cost before it returns 403. Tool arguments never go to Jev. Prompt and tool-result text go to Jev after redaction, so the call sees `[REDACTED]` and not the original secret. Assistant text goes to Jev only when the cheap checks left that span as Allow.

## OWASP LLM checks

| OWASP id | What this proxy does |
| --- | --- |
| LLM01 Prompt Injection | `ignore_previous` and `instruction_override` |
| LLM02 Sensitive Information Disclosure | Email and secret checks on the way out |
| LLM03 Supply Chain | `pickle` and `model_host` |
| LLM05 Improper Output Handling | Output scan |
| LLM06 Excessive Agency | Tool allowlist |
| LLM07 System Prompt Leakage | `instruction_override` |
| LLM10 Unbounded Consumption | USD cap |

## Dependency licenses

| Package | License |
| --- | --- |
| fastapi | MIT |
| httpx | BSD-3-Clause |
| PyYAML | MIT |
| uvicorn | BSD-3-Clause |
| pytest | MIT |
