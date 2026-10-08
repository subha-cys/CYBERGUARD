import json
import pytest
from detectors.contract import DetectorResult
from detectors.login import analyze_login
from detectors.url import analyze_url
from features.security import extract_security_features
from features.url import extract_url_features

REQUIRED_RESULT_FIELDS = {"detector", "detector_version", "method", "classification", "confidence",
                          "evidence", "features", "limitations", "processing_time_ms", "timestamp",
                          "model_version", "confidence_status"}


def assert_detector_contract(result):
    data = result.to_dict()
    assert REQUIRED_RESULT_FIELDS <= data.keys()
    assert data["detector"] and data["detector_version"] and data["classification"]
    assert data["confidence"] is None or 0 <= data["confidence"] <= 1
    assert data["processing_time_ms"] >= 0


def test_detector_contract_and_confidence_bounds():
    result = analyze_url("https://example.org/")
    data = result.to_dict()
    assert_detector_contract(result)
    assert result.confidence is None or 0 <= result.confidence <= 1
    with pytest.raises(ValueError):
        DetectorResult("x", "1", "ml", "x", 1.1)


@pytest.mark.parametrize("url,expected", [
    ("https://example.org/home", "https"),
    ("http://192.0.2.8/login", "ip"),
    ("https://example.org/%2Flogin", "encoded"),
    ("https://example.org/" + "a" * 110, "long"),
    ("https://a.b.c.d.example.org/signin", "subdomains"),
    ("https://example.org/verify-account", "token"),
])
def test_url_features(url, expected):
    features = extract_url_features(url)
    if expected == "https": assert features["https_scheme"]
    elif expected == "ip": assert features["ip_literal_host"]
    elif expected == "encoded": assert features["encoded_character_count"] > 0
    elif expected == "long": assert features["url_length"] > 100
    elif expected == "subdomains": assert features["subdomain_count"] >= 3
    elif expected == "token": assert "verify" in features["suspicious_tokens"]


def test_url_bad_inputs_and_never_fetches():
    for bad in ("", "https:///", "https://bad\n.example"):
        with pytest.raises(ValueError): extract_url_features(bad)
    out = analyze_url("http://192.0.2.5/login").to_dict()
    assert out["classification"] == "suspicious_indicators"
    assert any("not prove" in limitation for limitation in out["limitations"])
    assert out["confidence"] is None
    assert out["features"]["malicious_url_probability"] is None
    assert 0 <= out["features"]["malicious_url_indicator_score"] <= 1


def test_security_features_are_separate_indicators():
    f = extract_security_features("Urgent: verify your account password using attached invoice https://other.invalid", "help@example.org", "https://other.invalid")
    assert f["urgency"] and f["credential_request"] and f["financial_request"]
    assert f["url_presence"] and f["sender_domain_mismatch"] and f["attachment_indicator"]


def test_phishing_security_rule_detector_has_independent_contract():
    from detectors.phishing_rules import PhishingSecurityRulesDetector
    result = PhishingSecurityRulesDetector().analyze("Urgent password verification required", "help@brand.test", "http://192.0.2.1/login")
    assert_detector_contract(result)
    assert result.method == "rule" and result.detector == "phishing_security_rules"
    assert result.classification == "security_indicators"
    assert result.confidence is None and all(item["type"] == "security_rule" for item in result.evidence)


def test_login_rules_and_validation():
    event = {"user_id": "synthetic", "timestamp": "2026-01-01T03:00:00Z", "ip": "192.0.2.10", "country": "ZZ", "device_id": "d", "failed_attempts": 6, "successful_login": True}
    out = analyze_login(event)
    assert_detector_contract(out)
    assert out.classification == "anomalous_indicators"
    assert out.confidence is None and out.features["history_available"] is False
    assert len(out.evidence) >= 2
    with pytest.raises(ValueError): analyze_login({"user_id": "x"})


def test_synthetic_login_generator_is_reproducible():
    from datasets.login_synthetic import generate_login_events
    assert generate_login_events(30, seed=5) == generate_login_events(30, seed=5)
    assert sum(x["ground_truth_anomaly"] for x in generate_login_events(30)) == 6


def test_login_ml_roundtrip_with_synthetic_model(tmp_path):
    pytest.importorskip("sklearn")
    from training.login import evaluate_isolation_forest
    from detectors.login_ml import LoginIsolationForestDetector
    from datasets.login_synthetic import generate_login_events
    evaluate_isolation_forest(n=100, output_dir=tmp_path / "login")
    detector = LoginIsolationForestDetector(tmp_path / "login" / "model.joblib")
    event = generate_login_events(20)[0]
    event.pop("ground_truth_anomaly")
    result = detector.analyze(event)
    assert_detector_contract(result)
    assert result.method == "ml" and result.model_version == "login-iforest-synthetic-1.0.0"
    assert result.confidence is None
    assert "decision_function_score_higher_is_more_normal" in result.features
