"""Transparent login anomaly rules; no user history is fabricated."""
import ipaddress
import time
from datetime import datetime
from detectors.contract import DetectorResult

DETECTOR_VERSION = "login-rules-1.0.0"


def analyze_login(event: dict) -> DetectorResult:
    required = {"user_id", "timestamp", "ip", "country", "device_id", "failed_attempts", "successful_login"}
    if not isinstance(event, dict) or required - event.keys():
        raise ValueError(f"login event missing required fields: {', '.join(sorted(required - event.keys()) if isinstance(event, dict) else sorted(required))}")
    if not isinstance(event["user_id"], str) or not event["user_id"].strip():
        raise ValueError("user_id must be a non-empty string")
    if isinstance(event["failed_attempts"], bool) or not isinstance(event["failed_attempts"], int) or event["failed_attempts"] < 0:
        raise ValueError("failed_attempts must be a non-negative integer")
    if not isinstance(event["successful_login"], bool):
        raise ValueError("successful_login must be boolean")
    try:
        stamp = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
        ipaddress.ip_address(event["ip"])
    except (ValueError, TypeError) as exc:
        raise ValueError("timestamp must be ISO-8601 and ip must be a valid address") from exc
    start = time.perf_counter()
    hour = stamp.hour
    rules = {
        "repeated_failures": event["failed_attempts"] >= 5,
        "successful_login_after_failures": event["successful_login"] and event["failed_attempts"] >= 3,
        "unusual_hour_indicator": hour < 5 or hour >= 23,
    }
    evidence = [{"type": "security_rule", "indicator": k, "value": True} for k, v in rules.items() if v]
    return DetectorResult(
        detector="login_anomaly", detector_version=DETECTOR_VERSION, method="rule",
        classification="anomalous_indicators" if evidence else "no_rule_indicators",
        confidence=None, confidence_status="not_applicable", evidence=evidence,
        features={"login_hour_utc": hour, "failed_attempts": event["failed_attempts"],
                  "successful_login": event["successful_login"], "country": event["country"],
                  "device_id_present": bool(event["device_id"]), "history_available": False},
        limitations=["No historical user baseline was supplied.", "Rules indicate triage signals, not confirmed account takeover."],
        processing_time_ms=(time.perf_counter() - start) * 1000,
    )
