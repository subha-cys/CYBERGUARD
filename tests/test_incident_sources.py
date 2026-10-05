import json
import sqlite3

from database.incidents import IncidentStore


def qualifying_analysis():
    return {
        "risk": {
            "incident_required": True,
            "severity": "high",
            "risk_score": 62,
        },
        "fusion": {
            "threat": "phishing",
            "evidence": [],
            "detector_results": [],
        },
        "explanation": {},
        "response": [],
    }


def test_incident_queue_filters_demos_and_legacy_unverified_rows(tmp_path):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    live = store.create_if_required(
        qualifying_analysis(),
        source="live_analysis",
        input_summary={"type": "email", "sender": "security@example.org"},
    )
    store.create_if_required(qualifying_analysis(), source="demo")

    with sqlite3.connect(store.path) as db:
        db.execute(
            "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "2026-01-01T00:00:00+00:00", "phishing", "high", 60, "open",
             json.dumps({"incident_id": "legacy", "status": "open"})),
        )

    incidents = store.list(source="live_analysis")
    assert [item["incident_id"] for item in incidents] == [live["incident_id"]]
    assert incidents[0]["input_summary"] == {"type": "email", "sender": "security@example.org"}
