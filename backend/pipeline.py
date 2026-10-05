"""Connect detector outputs through fusion, risk, explanation, response, and incidents."""
from datetime import datetime, timezone
from fusion.engine import fuse
from risk.engine import RiskEngine
from explainability.engine import explain
from response.engine import recommend
from database.incidents import IncidentStore


def analyze(detector_results: list[dict], asset_sensitivity: str = "medium",
            incident_store: IncidentStore | None = None) -> dict:
    fusion = fuse(detector_results)
    risk = RiskEngine().assess(fusion, asset_sensitivity)
    response = recommend(fusion, risk)
    explanation = explain(fusion, risk, response)
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "fusion": fusion, "risk": risk,
              "explanation": explanation, "response": response, "incident": None}
    if incident_store:
        result["incident"] = incident_store.create_if_required(result)
    return result
