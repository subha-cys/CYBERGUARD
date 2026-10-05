"""Small SQLite incident store for local prototype workflows."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).with_name("incidents.sqlite3")
VALID_STATUSES = {"open", "acknowledged", "investigating", "triaged", "resolved"}


class IncidentStore:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                threat TEXT NOT NULL,
                severity TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )""")

    def create_if_required(
        self,
        analysis: dict,
        *,
        source: str = "live_analysis",
        input_summary: dict | None = None,
    ) -> dict | None:
        if not analysis["risk"]["incident_required"]:
            return None
        incident_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        detector_versions = [{"detector": x["detector"], "detector_version": x["detector_version"],
                              "model_version": x.get("model_version")}
                             for x in analysis["fusion"]["detector_results"]]
        incident = {
            "incident_id": incident_id, "timestamp": timestamp, "threat": analysis["fusion"]["threat"],
            "severity": analysis["risk"]["severity"], "risk_score": analysis["risk"]["risk_score"],
            "evidence": analysis["fusion"]["evidence"], "detector_outputs": analysis["fusion"]["detector_results"],
            "explanation": analysis["explanation"], "recommended_response": analysis["response"],
            "status": "open", "detector_versions": detector_versions, "source": source,
        }
        if input_summary:
            incident["input_summary"] = input_summary
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (incident_id, timestamp, incident["threat"], incident["severity"], incident["risk_score"],
                        incident["status"], json.dumps(incident)))
        return incident

    def get(self, incident_id: str) -> dict | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload_json FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, *, source: str | None = None) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload_json FROM incidents ORDER BY timestamp DESC").fetchall()
        incidents = [json.loads(row[0]) for row in rows]
        if source is not None:
            incidents = [incident for incident in incidents if incident.get("source") == source]
        return incidents

    def set_status(self, incident_id: str, status: str) -> dict:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload_json FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if not row:
                raise KeyError("incident not found")
            incident = json.loads(row[0])
            incident["status"] = status
            db.execute("UPDATE incidents SET status = ?, payload_json = ? WHERE incident_id = ?",
                       (status, json.dumps(incident), incident_id))
        return incident
