import json

import pytest

from backend.pipeline import analyze
from database.incidents import IncidentStore


def detector(name, label, evidence=(), confidence=0.8):
    return {"detector": name, "detector_version": "test-1", "model_version": "model-test" if "nlp" in name or "iforest" in name else None,
            "method": "test fixture", "classification": label, "confidence": confidence,
            "confidence_status": "available" if confidence is not None else "unavailable",
            "evidence": list(evidence), "features": {}, "limitations": ["synthetic test fixture"]}


def test_six_scenario_logic_and_incidents(tmp_path):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    cases = {
        "A": [detector("phishing_nlp", "benign"), detector("phishing_security_rules", "no_security_indicators")],
        "B": [detector("phishing_nlp", "phishing", [{"indicator": "credential_request"}]),
              detector("phishing_security_rules", "security_indicators", [{"indicator": "credential_request"}, {"indicator": "urgency"}])],
        "C": [detector("phishing_nlp", "phishing", [{"indicator": "credential_request"}]),
              detector("phishing_security_rules", "security_indicators", [{"indicator": "credential_request"}, {"indicator": "sender_domain_mismatch"}]),
              detector("url_lexical", "suspicious_indicators", [{"indicator": "suspicious_url", "value": "192.0.2.5"}])],
        "D": [detector("login_anomaly", "no_rule_indicators"), detector("login_anomaly_iforest", "no_model_anomaly")],
        "E": [detector("login_anomaly", "anomalous_indicators", [{"indicator": "repeated_failures"}]), detector("login_anomaly_iforest", "no_model_anomaly")],
        "F": [detector("login_anomaly", "anomalous_indicators", [{"indicator": "repeated_failures"}, {"indicator": "successful_login_after_failures"}, {"indicator": "unusual_hour_indicator"}]),
              detector("login_anomaly_iforest", "anomalous_indicators", [{"indicator": "isolation_forest_outlier"}])],
    }
    results = {key: analyze(value, incident_store=store) for key, value in cases.items()}
    assert results["A"]["fusion"]["threat"] == "benign"
    assert results["A"]["risk"]["risk_score"] == 0
    assert results["B"]["fusion"]["threat"] == "phishing" and results["B"]["incident"]
    assert results["C"]["fusion"]["supporting_detectors"] == ["phishing_nlp", "phishing_security_rules", "url_lexical"]
    assert results["C"]["incident"]["severity"] == "critical"
    assert results["D"]["fusion"]["threat"] == "no_threat_detected" and results["D"]["risk"]["risk_score"] == 0
    assert results["E"]["fusion"]["conflicting_detectors"] == ["login_anomaly_iforest"]
    assert results["F"]["risk"]["severity"] == "critical" and results["F"]["incident"]
    assert results["F"]["fusion"]["confidence_values_are_not_averaged"]
    for result in results.values():
        assert all(x["approval_required"] and not x["automatic_execution"] for x in result["response"])
        for item in result["explanation"]["evidence"]:
            assert any(item["detector"] == source["detector"] and item["indicator"] == source.get("indicator")
                       and item["value"] == source.get("value") for source in result["fusion"]["evidence"])
    incident = results["C"]["incident"]
    assert incident["status"] == "open" and incident["detector_versions"] and incident["recommended_response"]
    assert store.get(incident["incident_id"])["evidence"] == incident["evidence"]
    assert store.set_status(incident["incident_id"], "triaged")["status"] == "triaged"
    assert len(store.list()) == 3


def test_risk_policy_levels_and_validation(tmp_path):
    from risk.engine import RiskEngine
    policy = tmp_path / "invalid.json"
    policy.write_text(json.dumps({"levels": [{"name": "all", "min": 0, "max": 50}], "incident_min_score": 50}), encoding="utf-8")
    with pytest.raises((KeyError, ValueError)):
        RiskEngine(policy)
