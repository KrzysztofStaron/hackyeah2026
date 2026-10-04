from control.explain import check_label, decision_label, human_event, render_text


def test_decision_and_check_read_in_plain_english() -> None:
    assert decision_label("block") == "Stopped"
    assert decision_label("redact") == "Scrubbed, then continued"
    assert "customer table" in check_label("signatures.table_wipe").lower() or "dataset" in check_label("signatures.table_wipe").lower()
    assert "secret" in check_label("secrets").lower()


def test_human_event_and_text_export() -> None:
    event = {
        "ts": "2026-10-04T02:50:00Z",
        "agent": "demo",
        "model": "gpt-4o-mini",
        "decision": "block",
        "check": "signatures.ignore_previous",
        "latency_ms": 42,
        "usd": 0.0001,
    }
    human = human_event(event)
    assert human["what"] == "Stopped"
    assert "override" in str(human["why"]).lower() or "injection" in str(human["why"]).lower()
    text = render_text([event])
    assert "Stopped" in text
    assert "demo" in text
    assert "Why:" in text
