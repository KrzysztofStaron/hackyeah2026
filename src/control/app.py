from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from control.audit import report
from control.budget import Spend, read, write
from control.controls import BY_PRESET, CONTROLS, PRESETS, matching_preset
from control import desk_db
from control.pipeline import handle
from control.policy import clear as clear_policy
from control.policy import refresh as refresh_policy
from control.policy import write_settings
from control.signatures import clear as clear_signatures
from control.workbook import preview

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
    return _page("index.html")


@app.get("/v1/report")
def show_report() -> JSONResponse:
    policy = refresh_policy(_policy_path())
    book = read(_data_dir() / "budget.json")
    if policy is None:
        payload = report("", "", {}, book, _data_dir() / "audit.jsonl")
        return JSONResponse(payload)
    payload = report(policy.profile, policy.loaded_at, policy.levels, book, _data_dir() / "audit.jsonl")
    payload["email_action"] = policy.level("pii")
    payload["usd_cap"] = policy.agents["demo"].usd_cap if "demo" in policy.agents else 0.0
    payload["roster"] = {
        name: {
            "enabled": agent.enabled,
            "usd_cap": agent.usd_cap,
            "tools": sorted(agent.tools),
        }
        for name, agent in policy.agents.items()
    }
    spent = payload.get("agents")
    if not isinstance(spent, dict):
        spent = {}
    payload["budget"] = [
        {
            "agent": name,
            "usd": _usd(spent.get(name)),
            "usd_cap": agent.usd_cap,
        }
        for name, agent in policy.agents.items()
    ]
    return JSONResponse(payload)


@app.get("/v1/demo/numbers")
def demo_numbers() -> JSONResponse:
    desk_db.ensure()
    snap = desk_db.snapshot()
    invoices = snap["invoices"]
    if not isinstance(invoices, dict):
        return JSONResponse(preview())
    return JSONResponse(invoices)


@app.get("/v1/demo/desk")
def demo_desk() -> JSONResponse:
    return JSONResponse(desk_db.snapshot())


@app.post("/v1/demo/desk/reset")
def reset_desk() -> JSONResponse:
    return JSONResponse(desk_db.reset())


@app.post("/v1/demo/desk/act")
async def act_desk(request: Request) -> JSONResponse:
    payload = _body(await request.json())
    raw = payload.get("tools")
    calls: list[dict[str, object]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                calls.append(item)
    return JSONResponse(desk_db.apply_tools(calls))


@app.post("/v1/demo/reset")
def reset_demo() -> JSONResponse:
    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    (data / "audit.jsonl").write_text("", encoding="utf-8")
    budget = data / "budget.json"
    if budget.is_file():
        budget.unlink()
    desk_db.reset()
    return JSONResponse({"reset": True})


@app.post("/v1/demo/exhaust")
def exhaust_budget() -> JSONResponse:
    policy = refresh_policy(_policy_path())
    if policy is None or "demo" not in policy.agents:
        return JSONResponse(status_code=503, content={"error": "policy.invalid"})
    path = _data_dir() / "budget.json"
    book = read(path)
    current = book.get("demo", Spend(0.0, 0))
    book["demo"] = Spend(policy.agents["demo"].usd_cap, current.tokens)
    write(path, book)
    return JSONResponse({"agent": "demo", "usd": policy.agents["demo"].usd_cap})


def _usd(item: object) -> float:
    if not isinstance(item, dict):
        return 0.0
    usd = item.get("usd")
    if isinstance(usd, bool) or not isinstance(usd, (int, float)):
        return 0.0
    return float(usd)


@app.get("/v1/settings")
def show_settings() -> JSONResponse:
    policy = refresh_policy(_policy_path())
    if policy is None:
        return JSONResponse(status_code=503, content={"error": "policy.invalid"})
    return JSONResponse(_settings(policy))


@app.put("/v1/settings")
async def save_settings(request: Request) -> JSONResponse:
    payload: object = await request.json()
    body = _body(payload)
    chosen = body.get("preset")
    if isinstance(chosen, str):
        preset = BY_PRESET.get(chosen)
        if preset is None or not write_settings(
            _policy_path(),
            preset.levels,
            preset.usd_cap,
            preset.id,
            preset.require_high_confidence,
        ):
            return JSONResponse(status_code=400, content={"error": "settings.invalid"})
        policy = refresh_policy(_policy_path())
        if policy is None:
            return JSONResponse(status_code=503, content={"error": "policy.invalid"})
        return JSONResponse(_settings(policy))
    incoming = body.get("controls")
    usd_cap = body.get("usd_cap")
    if not isinstance(incoming, dict) or isinstance(usd_cap, bool) or not isinstance(usd_cap, (int, float)):
        return JSONResponse(status_code=400, content={"error": "settings.invalid"})
    current = refresh_policy(_policy_path())
    if current is None:
        return JSONResponse(status_code=503, content={"error": "policy.invalid"})
    levels = dict(current.levels)
    for key, item in incoming.items():
        if isinstance(key, str) and isinstance(item, str):
            levels[key] = item
    cap = float(usd_cap)
    incoming_flag = body.get("require_high_confidence")
    require_high_confidence = incoming_flag if isinstance(incoming_flag, bool) else current.require_high_confidence
    profile = matching_preset(levels, cap, require_high_confidence) or "custom"
    if not write_settings(_policy_path(), levels, cap, profile, require_high_confidence):
        return JSONResponse(status_code=400, content={"error": "settings.invalid"})
    policy = refresh_policy(_policy_path())
    if policy is None:
        return JSONResponse(status_code=503, content={"error": "policy.invalid"})
    return JSONResponse(_settings(policy))


def _cap(policy: object) -> float:
    agents = getattr(policy, "agents", {})
    demo = agents.get("demo") if isinstance(agents, dict) else None
    if demo is None:
        return 0.0
    return float(demo.usd_cap)


def _settings(policy: object) -> dict[str, object]:
    levels = getattr(policy, "levels", {})
    usd_cap = _cap(policy)
    require_high_confidence = getattr(policy, "require_high_confidence", False) is True
    if not isinstance(levels, dict):
        levels = {}
    return {
        "usd_cap": usd_cap,
        "require_high_confidence": require_high_confidence,
        "preset": matching_preset(levels, usd_cap, require_high_confidence),
        "presets": [
            {
                "id": item.id,
                "label": item.label,
                "usd_cap": item.usd_cap,
                "controls": item.levels,
                "require_high_confidence": item.require_high_confidence,
            }
            for item in PRESETS
        ],
        "controls": [
            {
                "id": item.id,
                "label": item.label,
                "tip": item.tip,
                "explains": item.explains,
                "mode": levels[item.id],
            }
            for item in CONTROLS
        ],
    }


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


def seed_catalog() -> None:
    root = _root()
    policy = _policy_path()
    signatures = _signatures_path()
    if not policy.is_file():
        _write(policy, _read(root / "policy" / "standard.yaml"))
    if not signatures.is_file():
        _write(signatures, _read(root / "signatures.json"))


def boot_default_defenses() -> None:
    """Start from Default so a leftover No-security edit does not greet judges."""
    preset = BY_PRESET["default"]
    path = _policy_path()
    if not path.is_file():
        return
    write_settings(
        path,
        preset.levels,
        preset.usd_cap,
        preset.id,
        preset.require_high_confidence,
    )
    reset_caches()


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
boot_default_defenses()
app.mount("/assets", StaticFiles(directory=Path(__file__).resolve().parents[2] / "static"), name="assets")
