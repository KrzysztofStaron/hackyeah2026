from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from control.audit import report
from control.budget import read
from control.pipeline import handle
from control.policy import clear as clear_policy
from control.policy import refresh as refresh_policy
from control.signatures import clear as clear_signatures

app = FastAPI()


def load_env() -> None:
    needed = ("OPENAI_APIKEY", "VERCEL_APIKEY")
    if all(os.environ.get(name) for name in needed):
        return
    roots = (Path.cwd(), Path(__file__).resolve().parents[2])
    for root in roots:
        path = root / ".env.local"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "" or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in needed and not os.environ.get(key):
                os.environ[key] = value


def reset_caches() -> None:
    clear_policy()
    clear_signatures()


def _policy_path() -> Path:
    return Path(os.environ.get("POLICY_PATH", "policy/standard.yaml"))


def _signatures_path() -> Path:
    return Path(os.environ.get("SIGNATURES_PATH", "signatures.json"))


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))


@app.get("/")
def index() -> HTMLResponse:
    page = Path(__file__).resolve().parents[2] / "static" / "index.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/v1/report")
def show_report() -> JSONResponse:
    policy = refresh_policy(_policy_path())
    book = read(_data_dir() / "budget.json")
    if policy is None:
        payload = report("", "", {"data_email": False, "data_secret": False, "signatures": False, "jev": False}, book, _data_dir() / "audit.jsonl")
        return JSONResponse(payload)
    controls = {
        "data_email": policy.data_email.enabled,
        "data_secret": policy.data_secret.enabled,
        "signatures": policy.signatures_enabled,
        "jev": policy.jev.enabled,
    }
    payload = report(policy.profile, policy.loaded_at, controls, book, _data_dir() / "audit.jsonl")
    return JSONResponse(payload)


@app.get("/v1/audit/export")
def export_audit() -> Response:
    path = _data_dir() / "audit.jsonl"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return Response(content=text, media_type="text/plain")


@app.post("/v1/chat/completions")
async def chat(request: Request) -> JSONResponse:
    payload: object = await request.json()
    body = _body(payload)
    status, content = handle(
        request.headers.get("x-agent-id"),
        body,
        _policy_path(),
        _signatures_path(),
        _data_dir(),
        os.environ.get("OPENAI_APIKEY", ""),
        os.environ.get("VERCEL_APIKEY", ""),
    )
    return JSONResponse(status_code=status, content=content)


def _body(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    body: dict[str, object] = {}
    for key, item in payload.items():
        if isinstance(key, str):
            body[key] = item
    return body


load_env()
