from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from control.audit import report
from control.budget import read
from control.pipeline import handle
from control.policy import clear as clear_policy
from control.policy import parse_policy
from control.policy import refresh as refresh_policy
from control.signatures import clear as clear_signatures
from control.signatures import parse_signatures

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


def _page(name: str) -> HTMLResponse:
    page = Path(__file__).resolve().parents[2] / "static" / name
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/")
def index() -> HTMLResponse:
    return _page("desk.html")


@app.get("/desk")
def desk() -> HTMLResponse:
    return _page("desk.html")


@app.get("/console")
def console() -> HTMLResponse:
    return _page("index.html")


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
    payload["email_action"] = policy.data_email.action
    payload["secret_action"] = policy.data_secret.action
    payload["jev_thresholds"] = policy.jev.thresholds
    payload["roster"] = {
        name: {
            "enabled": agent.enabled,
            "usd_cap": agent.usd_cap,
            "call_cap": agent.call_cap,
            "tools": sorted(agent.tools),
        }
        for name, agent in policy.agents.items()
    }
    return JSONResponse(payload)


@app.get("/v1/catalog")
def show_catalog() -> JSONResponse:
    root = _root()
    return JSONResponse(
        {
            "policy": _read(_policy_path()),
            "signatures": _read(_signatures_path()),
            "standard": _read(root / "policy" / "standard.yaml"),
            "strict": _read(root / "policy" / "strict.yaml"),
        }
    )


@app.put("/v1/catalog")
async def save_catalog(request: Request) -> JSONResponse:
    payload: object = await request.json()
    body = _body(payload)
    saved: list[str] = []
    policy_text = body.get("policy")
    if isinstance(policy_text, str):
        if _policy_text(policy_text) is None:
            return JSONResponse(status_code=400, content={"error": "policy.invalid"})
        _write(_policy_path(), policy_text)
        clear_policy()
        saved.append("policy")
    signature_text = body.get("signatures")
    if isinstance(signature_text, str):
        if _signature_text(signature_text) is None:
            return JSONResponse(status_code=400, content={"error": "signatures.invalid", "saved": saved})
        _write(_signatures_path(), signature_text)
        clear_signatures()
        saved.append("signatures")
    if not saved:
        return JSONResponse(status_code=400, content={"error": "catalog.empty"})
    return JSONResponse({"saved": saved})


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
        request.headers.get("x-request-id") or "",
    )
    return JSONResponse(status_code=status, content=content)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _policy_text(text: str) -> object:
    try:
        loaded: object = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return parse_policy(loaded)


def _signature_text(text: str) -> object:
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parse_signatures(loaded)


def seed_catalog() -> None:
    root = _root()
    policy = _policy_path()
    signatures = _signatures_path()
    if not policy.is_file():
        _write(policy, _read(root / "policy" / "standard.yaml"))
    if not signatures.is_file():
        _write(signatures, _read(root / "signatures.json"))


def _body(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    body: dict[str, object] = {}
    for key, item in payload.items():
        if isinstance(key, str):
            body[key] = item
    return body


load_env()
seed_catalog()
app.mount("/assets", StaticFiles(directory=Path(__file__).resolve().parents[2] / "static"), name="assets")
