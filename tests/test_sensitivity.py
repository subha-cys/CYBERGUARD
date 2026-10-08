from risk.sensitivity import infer_asset_sensitivity


def test_sensitivity_uses_medium_when_media_content_is_not_inspectable():
    result = infer_asset_sensitivity({
        "type": "audio",
        "filename": "meeting.wav",
        "content_base64": "password=supersecret@example.com",
    })
    assert result["level"] == "medium"
    assert result["indicators"] == []


def test_sensitivity_escalates_for_observed_credentials_without_returning_values():
    result = infer_asset_sensitivity({
        "type": "email",
        "raw_message": "Password: Summer-Secret-2026",
    })
    assert result["level"] == "critical"
    assert result["indicators"] == ["credential_or_secret_value"]
    assert "Summer-Secret-2026" not in result["reason"]


def test_sensitivity_escalates_for_contact_information():
    result = infer_asset_sensitivity({"type": "sms", "text": "Reach Alice at alice@example.org"})
    assert result["level"] == "high"
    assert "personal_contact_information" in result["indicators"]


def test_sensitivity_detects_card_and_identified_medical_records():
    card = infer_asset_sensitivity({"type": "email", "text": "Card number 4111 1111 1111 1111"})
    medical = infer_asset_sensitivity({
        "type": "email",
        "text": "Patient record: diagnosis for alice@example.org",
    })
    assert card["level"] == "critical"
    assert "payment_card_number" in card["indicators"]
    assert medical["level"] == "critical"
    assert "identified_medical_information" in medical["indicators"]


def test_sensitivity_ignores_client_supplied_level():
    result = infer_asset_sensitivity({"type": "url", "url": "https://example.org", "asset_sensitivity": "critical"})
    assert result["level"] == "medium"
