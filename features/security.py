"""Explainable security indicators; never substitutes for the NLP model."""
import re
from email.utils import parseaddr
from urllib.parse import urlparse

SECURITY_FEATURE_VERSION = "security-text-2.0.0"
PATTERNS = {
    "urgency": re.compile(
        r"\b(urgent|immediately|act now|within \d+ hours?|within 24 hours|suspended|locked|expires? soon|final notice|immediate action|account suspended)\b",
        re.I,
    ),
    "credential_request": re.compile(
        r"\b(password|verify your account|sign in|login credentials|security code|credentials|confirm your identity)\b",
        re.I,
    ),
    "otp_request": re.compile(
        r"\b(otp|one[- ]time password|verification code|2fa code|security token|auth code|mfa code|sms code)\b",
        re.I,
    ),
    "financial_request": re.compile(
        r"\b(payment|wire transfer|bank account|invoice|gift card|unpaid fee|toll fee|refund|crypto|wallet)\b",
        re.I,
    ),
    "impersonation_language": re.compile(
        r"\b(ceo|chief executive|it support|help desk|your bank|security team|usps|fedex|dhl|ups|netflix|paypal|apple support|microsoft account)\b",
        re.I,
    ),
    "attachment_indicator": re.compile(r"\b(attachment|attached|\.\w{2,5}\b)", re.I),
    "suspicious_wording": re.compile(
        r"\b(click here|confirm now|avoid (?:account )?closure|unusual activity|claim reward|package pending|action required)\b",
        re.I,
    ),
    "smishing_indicators": re.compile(
        r"\b(reply stop|text stop|package delivery|delivery attempt|toll charge|unclaimed parcel|reschedule delivery)\b",
        re.I,
    ),
    "quishing_indicators": re.compile(
        r"\b(scan the qr|scan qr|scan to verify|scan with your phone|scan code|camera to scan)\b",
        re.I,
    ),
}


def extract_security_features(text: str, sender: str | None = None, displayed_url: str | None = None) -> dict:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    features = {name: bool(pattern.search(text)) for name, pattern in PATTERNS.items()}
    features["url_presence"] = bool(displayed_url or re.search(r"https?://|www\.", text, re.I))
    features["sender_domain_mismatch"] = False
    if sender and displayed_url:
        address = parseaddr(sender)[1].lower()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""
        try:
            link_host = (urlparse(displayed_url if "://" in displayed_url else "//" + displayed_url).hostname or "").lower()
        except ValueError:
            link_host = ""
        features["sender_domain_mismatch"] = bool(domain and link_host and domain != link_host and not link_host.endswith("." + domain))
    return features
