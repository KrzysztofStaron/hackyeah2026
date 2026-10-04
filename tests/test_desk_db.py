from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from control import desk_db
from control.app import app, reset_caches

CLIENT = TestClient(app)


def prepare(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    os.environ["DATA_DIR"] = str(data)
    reset_caches()
    desk_db.reset()
    return data


def test_snapshot_seeds_invoices_as_rows(tmp_path: Path) -> None:
    prepare(tmp_path)
    snap = desk_db.snapshot()
    invoices = snap["invoices"]
    assert isinstance(invoices, dict)
    assert invoices["columns"] == ["id", "customer", "amount", "status"]
    assert len(invoices["row"]) == 8
    first = invoices["row"][0]
    assert first["id"] == "INV-1001"
    assert first["amount"] == 2400
    assert first["status"] == "open"
    company = snap["company"]
    assert isinstance(company, dict)
    assert len(company["customers"]) == 2


def test_edit_workbook_updates_an_invoice(tmp_path: Path) -> None:
    prepare(tmp_path)
    result = desk_db.edit_workbook(invoice_id="INV-1001", amount=42)
    assert result["ok"] is True
    snap = desk_db.snapshot()
    invoices = snap["invoices"]
    assert isinstance(invoices, dict)
    row = {item["id"]: item for item in invoices["row"]}
    assert row["INV-1001"]["amount"] == 42


def test_lookup_customer_accepts_name_or_account(tmp_path: Path) -> None:
    prepare(tmp_path)
    by_name = desk_db.lookup_customer("Jan Kowalski")
    assert by_name["ok"] is True
    customer = by_name["customer"]
    assert isinstance(customer, dict)
    assert customer["account"] == "4418"
    by_account = desk_db.lookup_customer("4418")
    assert by_account["ok"] is True
    found = by_account["customer"]
    assert isinstance(found, dict)
    assert found["name"] == "Jan Kowalski"
    missing = desk_db.lookup_customer("nobody")
    assert missing["ok"] is False


def test_run_sql_sums_open_invoices(tmp_path: Path) -> None:
    prepare(tmp_path)
    result = desk_db.run_sql(
        "SELECT SUM(amount) AS total FROM invoices WHERE status = 'open'"
    )
    assert result["ok"] is True
    assert result["rows"][0]["total"] == 2400 + 1850 + 3100 + 1275 + 2100


def test_run_sql_deletes_customers_and_snapshot_reflects(tmp_path: Path) -> None:
    prepare(tmp_path)
    result = desk_db.run_sql("DELETE FROM customers")
    assert result["ok"] is True
    snap = desk_db.snapshot()
    company = snap["company"]
    assert isinstance(company, dict)
    assert company["customers"] == []


def test_apply_tools_returns_updated_desk(tmp_path: Path) -> None:
    prepare(tmp_path)
    payload = desk_db.apply_tools(
        [{"name": "edit_workbook", "arguments": {"id": "INV-1002", "amount": 7}}]
    )
    assert payload["results"][0]["ok"] is True
    desk = payload["desk"]
    assert isinstance(desk, dict)
    invoices = desk["invoices"]
    assert isinstance(invoices, dict)
    row = {item["id"]: item for item in invoices["row"]}
    assert row["INV-1002"]["amount"] == 7


def test_desk_act_endpoint_updates_sqlite(tmp_path: Path) -> None:
    prepare(tmp_path)
    response = CLIENT.post(
        "/v1/demo/desk/act",
        json={
            "tools": [
                {
                    "name": "run_sql",
                    "arguments": {
                        "sql": "UPDATE invoices SET amount = 99 WHERE id = 'INV-1003'"
                    },
                }
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["ok"] is True
    row = {item["id"]: item for item in body["desk"]["invoices"]["row"]}
    assert row["INV-1003"]["amount"] == 99


def test_http_request_fetches_a_url(tmp_path: Path) -> None:
    prepare(tmp_path)
    result = desk_db.http_request("https://example.com", method="GET")
    assert result["ok"] is True
    assert result["status"] == 200
    assert "Example Domain" in str(result["body"])


def test_desk_act_runs_http_request(tmp_path: Path) -> None:
    prepare(tmp_path)
    response = CLIENT.post(
        "/v1/demo/desk/act",
        json={
            "tools": [
                {
                    "name": "http_request",
                    "arguments": {"url": "https://example.com", "method": "GET"},
                }
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["ok"] is True
    assert body["results"][0]["status"] == 200
