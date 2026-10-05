"""Independent deterministic email security indicators."""
import time
from detectors.contract import DetectorResult
from features.security import SECURITY_FEATURE_VERSION, extract_security_features

DETECTOR_VERSION = "phishing-security-rules-1.0.0"


class PhishingSecurityRulesDetector:
    def analyze(self, text: str, sender: str | None = None, displayed_url: str | None = None) -> DetectorResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("email text must be a non-empty string")
        start = time.perf_counter()
        features = extract_security_features(text, sender, displayed_url)
        evidence = [{"type": "security_rule", "indicator": key, "value": True}
                    for key, value in features.items() if value]
        return DetectorResult(
            detector="phishing_security_rules", detector_version=DETECTOR_VERSION, method="rule",
            classification="security_indicators" if evidence else "no_security_indicators",
            confidence=None, confidence_status="not_applicable", evidence=evidence,
            features={**features, "feature_version": SECURITY_FEATURE_VERSION},
            limitations=["Rules are independent indicators and do not prove maliciousness."],
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )
