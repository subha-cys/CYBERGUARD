"""Six synthetic end-to-end detector -> fusion -> risk -> response scenarios."""
import json
from pathlib import Path
from database.incidents import IncidentStore
from detectors.phishing import PhishingNLPDetector
from detectors.phishing_rules import PhishingSecurityRulesDetector
from detectors.url import analyze_url
from detectors.login import analyze_login
from detectors.login_ml import LoginIsolationForestDetector
from backend.pipeline import analyze


def _chain(name: str, input_data: dict, detector_results: list[dict], store: IncidentStore) -> dict:
    result = analyze(detector_results, input_data.get("asset_sensitivity", "medium"), store)
    return {"scenario": name, "input": input_data, "detector_results": detector_results,
            "evidence": result["fusion"]["evidence"], "fusion": result["fusion"], "risk": result["risk"],
            "explanation": result["explanation"], "response": result["response"], "incident": result["incident"]}


def run_demo(phishing_model: str, login_model: str, login_input: str = "datasets/demo_login.json",
             database_path: str = "database/incidents.sqlite3") -> dict:
    store = IncidentStore(database_path)
    text_detector = PhishingNLPDetector(phishing_model)
    rule_detector = PhishingSecurityRulesDetector()
    login_ml = LoginIsolationForestDetector(login_model)
    scenarios = []

    normal_email = "Quarterly planning meeting is Tuesday at 10 AM. Please review the revised agenda before joining."
    results = [text_detector.analyze(normal_email).to_dict(), rule_detector.analyze(normal_email).to_dict()]
    scenarios.append(_chain("A_normal_email", {"text": normal_email, "synthetic": True}, results, store))

    suspicious_email = "URGENT: Verify your account password immediately to prevent access suspension."
    results = [text_detector.analyze(suspicious_email).to_dict(), rule_detector.analyze(suspicious_email).to_dict()]
    scenarios.append(_chain("B_suspicious_phishing_email", {"text": suspicious_email, "synthetic": True}, results, store))

    phishing_email = "URGENT: Your mailbox is locked. Verify your account password now to avoid suspension."
    sender = "IT Support <alert@example.org>"
    url = "http://192.0.2.44/verify"
    results = [text_detector.analyze(phishing_email).to_dict(),
               rule_detector.analyze(phishing_email, sender, url).to_dict(), analyze_url(url).to_dict()]
    scenarios.append(_chain("C_phishing_with_suspicious_url_and_credentials",
                             {"text": phishing_email, "sender": sender, "url": url, "synthetic": True}, results, store))

    normal_login = {"user_id": "synthetic-user-01", "timestamp": "2026-01-01T10:00:00Z", "ip": "192.0.2.10",
                    "country": "ZZ", "device_id": "known-device", "failed_attempts": 0, "successful_login": True}
    login_results = [analyze_login(normal_login).to_dict(), login_ml.analyze(normal_login).to_dict()]
    scenarios.append(_chain("D_normal_login", {**normal_login, "synthetic": True}, login_results, store))

    suspicious_login = {"user_id": "synthetic-user-02", "timestamp": "2026-01-01T10:00:00Z", "ip": "192.0.2.20",
                        "country": "ZZ", "device_id": "new-device", "failed_attempts": 5, "successful_login": False}
    login_results = [analyze_login(suspicious_login).to_dict(), login_ml.analyze(suspicious_login).to_dict()]
    scenarios.append(_chain("E_suspicious_login", {**suspicious_login, "synthetic": True}, login_results, store))

    multi_login = {"user_id": "synthetic-user-03", "timestamp": "2026-01-01T03:00:00Z", "ip": "192.0.2.30",
                   "country": "ZZ", "device_id": "unseen-device", "failed_attempts": 7, "successful_login": True}
    login_results = [analyze_login(multi_login).to_dict(), login_ml.analyze(multi_login).to_dict()]
    scenarios.append(_chain("F_multiple_login_anomalies", {**multi_login, "synthetic": True}, login_results, store))

    return {"pipeline": ["input", "detectors", "evidence", "fusion", "risk", "explanation", "response"],
            "scenarios": scenarios, "created_incidents": len([x for x in scenarios if x["incident"]])}
