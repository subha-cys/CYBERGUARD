"""Comprehensive test suite for unified phishing and malicious website detection module."""
from __future__ import annotations

import pytest
from backend.service import analyze_request, run_demo
from detectors.url import analyze_url
from features.url import extract_url_features, extract_urls, check_brand_similarity, detect_url_mismatch
from features.webpage import extract_webpage_features


# -------------------------------------------------------------------------
# Test Case 1: Legitimate URL
# -------------------------------------------------------------------------
def test_case_1_legitimate_url():
    url = "https://example.org/about"
    html = "<!DOCTYPE html><html><head><title>Example Domain</title></head><body><h1>About Example</h1><p>General information.</p></body></html>"
    result = analyze_request({"type": "url", "url": url, "html_content": html})
    
    assert result["threat_category"] in {"benign", "undetermined", "no_threat_detected"}
    assert result["risk_score"] < 25
    assert result["risk_level"] == "LOW"
    assert result["malicious_url_probability"] < 0.15
    assert not any(e.get("indicator") == "lookalike_domain" for e in result["evidence"])
    assert not any(e.get("indicator") == "fake_login_page" for e in result["evidence"])


# -------------------------------------------------------------------------
# Test Case 2: Look-alike domain
# -------------------------------------------------------------------------
def test_case_2_lookalike_domain():
    url = "https://paypa1-security.com/signin"
    result = analyze_request({"type": "url", "url": url, "displayed_url": "https://paypal.com/signin"})
    
    assert result["risk_score"] >= 25
    assert result["malicious_url_probability"] >= 0.35
    evidence_indicators = {e.get("indicator") for e in result["evidence"]}
    assert "lookalike_domain" in evidence_indicators
    assert "url_mismatch" in evidence_indicators
    assert any("resembles" in r or "brand" in r.lower() for r in result["explanation"]["reasons"])


# -------------------------------------------------------------------------
# Test Case 3: Suspicious long URL
# -------------------------------------------------------------------------
def test_case_3_suspicious_long_url():
    url = "http://192.0.2.14/login/update/account/verify?token=3f89a2&session=%2F%3F%26auth%3Dtrue&redirect=http%3A%2F%2Fupdate-now.xyz%2Fauth#login-credentials-secure-token-id-99887766554433221100"
    result = analyze_request({"type": "url", "url": url})
    
    assert result["risk_score"] >= 25
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "long_url" in indicators
    assert "ip_literal_host" in indicators
    assert "suspicious_tokens" in indicators
    assert "encoded_characters" in indicators
    assert result["malicious_url_probability"] >= 0.30


# -------------------------------------------------------------------------
# Test Case 4: Fake login-page example
# -------------------------------------------------------------------------
def test_case_4_fake_login_page():
    url = "http://192.0.2.55/microsoft/login"
    html = """<!DOCTYPE html><html><head><title>Sign in to your Microsoft account</title></head>
    <body><h2>Sign in</h2>
    <form action="http://198.51.100.88/collect" method="POST">
      <label>Email, phone, or Skype</label><input type="text" name="loginfmt">
      <label>Password</label><input type="password" name="passwd">
      <label>Security PIN / OTP</label><input type="text" name="mfa_otp">
      <button type="submit">Sign in</button>
    </form></body></html>"""
    
    result = analyze_request({"type": "website", "url": url, "html_content": html})
    
    assert result["risk_score"] >= 50
    assert result["risk_level"] in {"HIGH", "CRITICAL"}
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "fake_login_page" in indicators
    assert "credential_fields_present" in indicators
    assert "external_form_action" in indicators
    assert "login_form_present" in indicators
    assert "block_url" in result["recommended_action"]


# -------------------------------------------------------------------------
# Test Case 5: Phishing email containing URL
# -------------------------------------------------------------------------
def test_case_5_phishing_email_containing_url():
    text = "URGENT: Your Office 365 mailbox has been suspended. Verify your account password immediately within 24 hours at http://192.0.2.44/verify to avoid permanent termination."
    sender = "IT Support <alert@untrusted-domain.xyz>"
    url = "http://192.0.2.44/verify"
    
    result = analyze_request({"type": "email", "text": text, "sender": sender, "url": url})
    
    assert result["risk_score"] >= 50
    assert result["risk_level"] in {"HIGH", "CRITICAL"}
    assert result["phishing_probability"] > 0.50
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "urgency" in indicators
    assert "credential_request" in indicators
    assert "ip_literal_host" in indicators
    assert "block_url" in result["recommended_action"]
    assert "quarantine_message" in result["recommended_action"]


# -------------------------------------------------------------------------
# Test Case 6: SMS phishing example (Smishing)
# -------------------------------------------------------------------------
def test_case_6_sms_phishing():
    text = "USPS Notice: Your package delivery is on hold due to an unpaid customs fee of $2.30. Reschedule delivery immediately at https://usps-parcel-redelivery.top/claim or reply STOP to cancel."
    sender = "+1-800-555-0199"
    
    result = analyze_request({"type": "sms", "text": text, "sender": sender})
    
    assert result["risk_score"] >= 25
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "smishing_indicators" in indicators
    assert "lookalike_domain" in indicators or "suspicious_tld" in indicators
    assert "quarantine_message" in result["recommended_action"]
    assert "warn_user" in result["recommended_action"]


# -------------------------------------------------------------------------
# Test Case 7: QR-code URL example (Quishing)
# -------------------------------------------------------------------------
def test_case_7_qr_code_phishing():
    payload = {
        "type": "qr_code",
        "text": "Security Warning: Scan the QR code below with your mobile camera to verify your MFA authenticator settings immediately: https://micros0ft-authenticator.xyz/mfa",
        "url": "https://micros0ft-authenticator.xyz/mfa"
    }
    result = analyze_request(payload)
    
    assert result["risk_score"] >= 50
    assert result["risk_level"] in {"HIGH", "CRITICAL"}
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "quishing_indicators" in indicators
    assert "lookalike_domain" in indicators or "suspicious_tld" in indicators
    assert "block_url" in result["recommended_action"]


# -------------------------------------------------------------------------
# Multi-URL message extraction & aggregation
# -------------------------------------------------------------------------
def test_multiple_urls_extraction_and_aggregation():
    text = "Check out our backup link at https://paypa1-update.com/login and the mirror at http://192.0.2.77/secure immediately!"
    extracted = extract_urls(text)
    assert len(extracted) == 2
    assert "https://paypa1-update.com/login" in extracted
    assert "http://192.0.2.77/secure" in extracted
    
    result = analyze_request({"type": "email", "text": text})
    indicators = {e.get("indicator") for e in result["evidence"]}
    assert "lookalike_domain" in indicators
    assert "ip_literal_host" in indicators
    # Both URLs contributed to the message risk
    assert result["malicious_url_probability"] > 0.40


# -------------------------------------------------------------------------
# Standard contract fields verification
# -------------------------------------------------------------------------
def test_standard_output_contract():
    result = run_demo("phishing_url")
    required_keys = [
        "phishing_probability",
        "malicious_url_probability",
        "risk_score",
        "risk_level",
        "threat_category",
        "evidence",
        "explanation",
        "recommended_action",
    ]
    for key in required_keys:
        assert key in result, f"Missing required top-level key: {key}"
    
    assert 0.0 <= result["phishing_probability"] <= 1.0
    assert 0.0 <= result["malicious_url_probability"] <= 1.0
    assert 0 <= result["risk_score"] <= 100
    assert result["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert isinstance(result["evidence"], list)
    assert isinstance(result["explanation"], dict)
    assert "reasons" in result["explanation"]
    assert isinstance(result["recommended_action"], list)

