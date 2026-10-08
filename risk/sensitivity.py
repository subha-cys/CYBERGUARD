"""Conservative, local-only asset sensitivity inference from submitted text."""
from __future__ import annotations

import re
from typing import Any


_SECRET_VALUE = re.compile(
    r"\b(?:password|passcode|otp|one[- ]time code|verification code|api[_ -]?key|access token|secret key)"
    r"\s*[:=]\s*([^\s,;]{4,})",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)")
_SSN = re.compile(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_MEDICAL_CONTEXT = re.compile(r"\b(?:diagnosis|patient record|medical record|prescription|lab results)\b", re.I)
_FINANCIAL_CONTEXT = re.compile(r"\b(?:bank account number|routing number|card number|payment card)\b", re.I)


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _text_values(value: Any, key: str = "") -> list[str]:
    if isinstance(value, dict):
        return [
            text
            for child_key, child in value.items()
            if child_key not in {"content_base64", "path", "filename", "asset_sensitivity"}
            for text in _text_values(child, str(child_key))
        ]
    if isinstance(value, list):
        return [text for child in value for text in _text_values(child, key)]
    if isinstance(value, str) and key not in {"content_base64", "path", "filename"}:
        return [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    return []


def infer_asset_sensitivity(payload: dict[str, Any]) -> dict[str, Any]:
    """Infer sensitivity without retaining matched values or inspecting media pixels/audio."""
    text = "\n".join(_text_values(payload))
    indicators: list[str] = []
    level = "medium"

    if _SECRET_VALUE.search(text):
        indicators.append("credential_or_secret_value")
    if _SSN.search(text):
        indicators.append("government_identifier")
    if any(_luhn_valid(match.group()) for match in _CARD_CANDIDATE.finditer(text)):
        indicators.append("payment_card_number")
    if _FINANCIAL_CONTEXT.search(text) and re.search(r"\b\d{6,}\b", text):
        indicators.append("financial_account_record")
    if _MEDICAL_CONTEXT.search(text) and (_EMAIL.search(text) or _PHONE.search(text) or _SSN.search(text)):
        indicators.append("identified_medical_information")

    if any(item in indicators for item in (
        "credential_or_secret_value",
        "government_identifier",
        "payment_card_number",
        "financial_account_record",
        "identified_medical_information",
    )):
        level = "critical"
    elif _EMAIL.search(text) or _PHONE.search(text):
        indicators.append("personal_contact_information")
        level = "high"

    if level == "critical":
        reason = "Sensitive credentials, financial data, or a direct personal identifier were detected in inspectable text."
    elif level == "high":
        reason = "Personal contact information was detected in inspectable text."
    else:
        reason = "No high-sensitivity data was confidently detected; medium is used when content cannot be fully inspected."

    return {
        "level": level,
        "method": "local_sensitive_content_rules",
        "indicators": list(dict.fromkeys(indicators)),
        "reason": reason,
    }
