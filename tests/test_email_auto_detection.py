import pytest

from backend.service import _detectors_for


def test_email_analysis_extracts_headers_claims_and_objectives_without_manual_fields():
    raw_message = (
        "From: Alex Example <alex@acmecorp.example>\n"
        "Subject: Payment request\n"
        "Authentication-Results: mx.example; spf=pass; dkim=pass; dmarc=pass\n\n"
        "I am the CEO at Acme Corp. Transfer the payment immediately."
    )
    detector_results, details = _detectors_for({"type": "email", "raw_message": raw_message})

    detected = details["auto_detected"]
    assert detected["sender"] == "alex@acmecorp.example"
    assert detected["sender_domain"] == "acmecorp.example"
    assert detected["sender_organization"] == "Acmecorp"
    assert detected["subject"] == "Payment request"
    assert detected["claimed_role"] == "executive"
    assert detected["claimed_organization"] == "Acme Corp"
    assert "financial_action_or_payment" in detected["objectives"]
    assert "urgent_response_requested" in detected["objectives"]
    assert all(item["detector"] != "identity_impersonation" for item in detector_results)


def test_email_analysis_does_not_guess_missing_sender_identity():
    detector_results, details = _detectors_for({
        "type": "email",
        "raw_message": "Please review the attached report when you have time.",
    })

    assert details["auto_detected"]["sender"] == "Not present in message"
    assert all(item["detector"] != "identity_impersonation" for item in detector_results)


def test_impersonation_analysis_type_is_no_longer_supported():
    with pytest.raises(ValueError, match="type must be"):
        _detectors_for({"type": "impersonation", "message_text": "Review this request."})
