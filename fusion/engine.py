"""Deterministic, version-agnostic fusion over the common detector contract."""
from collections import defaultdict
from datetime import datetime, timezone

FUSION_VERSION = "threat-fusion-1.2.0"

PHISHING_POSITIVE = {
    "phishing_nlp": {"phishing"},
    "url_lexical": {"suspicious_indicators"},
    "phishing_security_rules": {"security_indicators"},
}
PHISHING_NEGATIVE = {"phishing_nlp": {"benign", "safe", "legitimate"}}
LOGIN_POSITIVE = {
    "login_anomaly": {"anomalous_indicators"},
    "login_anomaly_iforest": {"anomalous_indicators"},
}
LOGIN_NEGATIVE = {
    "login_anomaly": {"no_rule_indicators"},
    "login_anomaly_iforest": {"no_model_anomaly"},
}
MEDIA_POSITIVE = {
    "multimedia_assessment": {"manipulation_indicators_detected", "manipulation_detected", "suspicious", "suspicious_indicators"},
}


def _validate(result: dict) -> None:
    required = {"detector", "detector_version", "method", "classification", "confidence", "evidence", "features", "limitations"}
    if not isinstance(result, dict) or required - result.keys():
        raise ValueError("detector output does not satisfy the common detector contract")
    if result["confidence"] is not None and not 0 <= result["confidence"] <= 1:
        raise ValueError("detector confidence must be null or in [0, 1]")
    if not isinstance(result["evidence"], list) or not isinstance(result["features"], dict):
        raise ValueError("detector evidence and features have invalid types")


def fuse(detector_results: list[dict]) -> dict:
    """Combine independent categorical signals; confidence values are never averaged.

    A phishing NLP positive contributes one ML vote; URL and security-rule positives
    are independent supporting signals. A benign NLP result conflicts only with a
    positive URL/rule signal. Login detectors form a separate account-takeover group.
    A final phishing classification requires a positive NLP output; rule/URL-only
    evidence is labelled suspicious_phishing. Any login positive is account_takeover
    risk, with agreement strength recorded separately.
    """
    if not isinstance(detector_results, list):
        raise ValueError("detector_results must be a list")
    normalized = []
    positives = defaultdict(list)
    negatives = defaultdict(list)
    for raw in detector_results:
        _validate(raw)
        name = raw["detector"]
        label = str(raw["classification"]).casefold()
        category = None
        signal = "neutral"
        if label in PHISHING_POSITIVE.get(name, set()):
            category, signal = "phishing", "support"
        elif label in PHISHING_NEGATIVE.get(name, set()):
            category, signal = "phishing", "conflict"
        elif label in LOGIN_POSITIVE.get(name, set()):
            category, signal = "account_takeover", "support"
        elif label in LOGIN_NEGATIVE.get(name, set()):
            category, signal = "account_takeover", "conflict"
        elif label in MEDIA_POSITIVE.get(name, set()):
            category = "multimedia_manipulation"
            signal = "support"
        voice_origin = raw["features"].get("voice_origin")
        voice_classification = voice_origin.get("classification") if isinstance(voice_origin, dict) else None
        voice_signal = {
            "likely_ai_generated": "support",
            "likely_human": "conflict",
        }.get(voice_classification, "neutral") if name == "multimedia_assessment" else "neutral"
        if voice_signal == "support":
            positives["synthetic_voice"].append(name)
        elif voice_signal == "conflict":
            negatives["synthetic_voice"].append(name)
        if category and signal == "support":
            positives[category].append(name)
        elif category and signal == "conflict":
            negatives[category].append(name)
        normalized.append({
            "detector": name, "detector_version": raw["detector_version"], "model_version": raw.get("model_version"),
            "method": raw["method"], "classification": raw["classification"], "normalized_threat": category,
            "normalized_signal": signal, "confidence": raw["confidence"],
            "confidence_status": raw.get("confidence_status", "unavailable"),
            "evidence": raw["evidence"], "features": raw["features"], "limitations": raw["limitations"],
            "voice_origin_signal": voice_signal,
        })

    categories = {}
    for category in {"phishing", "account_takeover", "multimedia_manipulation", "synthetic_voice"}:
        support = list(dict.fromkeys(positives[category]))
        # A benign/no-anomaly result is a disagreement only when another detector
        # in that threat family has raised a positive signal.
        conflict = list(dict.fromkeys(negatives[category])) if support else []
        if not support and not conflict:
            continue
        if support and conflict:
            agreement = "conflicting"
        elif len(support) >= 2:
            agreement = "multi_detector_agreement"
        elif support:
            agreement = "single_detector_support"
        else:
            agreement = "no_threat_signal"
        categories[category] = {"supporting_detectors": support, "conflicting_detectors": conflict,
                                "agreement": agreement, "support_count": len(support)}

    if "account_takeover" in categories and categories["account_takeover"]["support_count"]:
        threat = "account_takeover"
    elif "phishing" in categories and categories["phishing"]["support_count"]:
        threat = "phishing" if "phishing_nlp" in categories["phishing"]["supporting_detectors"] else "suspicious_phishing"
    elif negatives["phishing"]:
        threat = "benign"
    elif negatives["account_takeover"]:
        threat = "no_threat_detected"
    elif categories.get("synthetic_voice", {}).get("support_count", 0):
        threat = "synthetic_voice"
    elif categories.get("multimedia_manipulation", {}).get("support_count", 0):
        threat = "multimedia_manipulation"
    else:
        threat = "undetermined"

    evidence_items = []
    independent = set()
    for result in normalized:
        for evidence in result["evidence"]:
            item = {"detector": result["detector"], "detector_version": result["detector_version"],
                    "model_version": result["model_version"], **evidence}
            evidence_items.append(item)
            indicator = evidence.get("indicator")
            if indicator:
                independent.add((result["detector"], indicator))
    relevant = categories.get({"phishing": "phishing", "suspicious_phishing": "phishing",
                               "account_takeover": "account_takeover",
                               "multimedia_manipulation": "multimedia_manipulation",
                               "synthetic_voice": "synthetic_voice"}.get(threat, "phishing"), {})
    voice_origin = next(
        (result["features"]["voice_origin"] for result in normalized
         if isinstance(result["features"].get("voice_origin"), dict)),
        None,
    )
    return {
        "fusion_version": FUSION_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "threat": threat,
        "detector_results": normalized,
        "categories": categories,
        "voice_origin": voice_origin,
        "supporting_detectors": relevant.get("supporting_detectors", []),
        "conflicting_detectors": relevant.get("conflicting_detectors", []),
        "agreement": relevant.get("agreement", "no_signal"),
        "evidence": evidence_items,
        "evidence_count": len(evidence_items),
        "independent_signal_count": len(independent),
        "confidence_values_are_not_averaged": True,
    }
