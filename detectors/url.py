"""Unified lexical, domain, and webpage indicator detector."""
from __future__ import annotations

import time
from typing import Any
from detectors.contract import DetectorResult
from features.url import URL_FEATURE_VERSION, extract_url_features, detect_url_mismatch
from features.webpage import extract_webpage_features, WEBPAGE_FEATURE_VERSION

DETECTOR_VERSION = "url-unified-2.0.0"


def calculate_malicious_probability(evidence: list[dict[str, Any]]) -> float:
    """Compute calibrated malicious URL probability from observed indicators."""
    if not evidence:
        return 0.02
    weights = {
        "fake_login_page": 0.45,
        "lookalike_domain": 0.38,
        "external_form_action": 0.35,
        "homoglyph_domain": 0.32,
        "url_mismatch": 0.30,
        "ip_literal_host": 0.28,
        "credential_fields_present": 0.25,
        "excessive_redirects": 0.22,
        "suspicious_tld": 0.20,
        "login_form_present": 0.15,
        "suspicious_tokens": 0.15,
        "at_symbol_in_authority": 0.15,
        "many_subdomains": 0.12,
        "long_url": 0.10,
        "encoded_characters": 0.10,
        "brand_impersonation": 0.35,
    }
    raw_score = sum(weights.get(e.get("indicator", ""), 0.08) for e in evidence)
    # Bounded probabilistic saturation curve
    prob = round(1.0 - (1.0 / (1.0 + raw_score * 1.6)), 3)
    return min(0.99, max(0.01, prob))


def analyze_url(
    url: str,
    html_content: str | None = None,
    displayed_url: str | None = None,
    redirect_chain: list[str] | None = None,
) -> DetectorResult:
    start = time.perf_counter()
    f = extract_url_features(url)
    evidence: list[dict[str, Any]] = []

    # Standard lexical checks
    if f["url_length"] > 100:
        evidence.append({"type": "lexical_indicator", "indicator": "long_url", "value": f["url_length"]})
    if f["subdomain_count"] >= 3:
        evidence.append({"type": "lexical_indicator", "indicator": "many_subdomains", "value": f["subdomain_count"]})
    if f["ip_literal_host"]:
        evidence.append({"type": "lexical_indicator", "indicator": "ip_literal_host", "value": True})
    if f["suspicious_tokens"]:
        evidence.append({"type": "lexical_indicator", "indicator": "suspicious_tokens", "value": f["suspicious_tokens"]})
    if f["encoded_character_count"] > 0:
        evidence.append({"type": "lexical_indicator", "indicator": "encoded_characters", "value": f["encoded_character_count"]})
    if f["at_symbol_present"]:
        evidence.append({"type": "lexical_indicator", "indicator": "at_symbol_in_authority", "value": True})

    # Domain checks
    if f["is_lookalike"]:
        evidence.append({
            "type": "domain_indicator",
            "indicator": "lookalike_domain",
            "value": f["lookalike_reason"],
            "matched_brand": f["matched_brand"],
            "similarity_score": f["brand_similarity_score"],
        })
    if f["suspicious_tld"]:
        evidence.append({"type": "domain_indicator", "indicator": "suspicious_tld", "value": f["tld"]})
    if f["has_homoglyphs"] or f["is_punycode"]:
        evidence.append({"type": "domain_indicator", "indicator": "homoglyph_domain", "value": f["hostname"]})
    if displayed_url and detect_url_mismatch(displayed_url, url):
        evidence.append({"type": "domain_indicator", "indicator": "url_mismatch", "value": f"Displayed '{displayed_url}' differs from destination '{url}'"})
    if redirect_chain and len(redirect_chain) > 2:
        evidence.append({"type": "redirect_indicator", "indicator": "excessive_redirects", "value": len(redirect_chain)})

    # Webpage DOM checks if HTML content provided
    web_features = {}
    if html_content:
        web_features = extract_webpage_features(html_content, page_url=url)
        if web_features["is_fake_login_page"]:
            evidence.append({"type": "webpage_indicator", "indicator": "fake_login_page", "value": True})
        if web_features["has_login_form"]:
            evidence.append({"type": "webpage_indicator", "indicator": "login_form_present", "value": True})
        if web_features["credential_field_presence"]:
            evidence.append({
                "type": "webpage_indicator",
                "indicator": "credential_fields_present",
                "value": f"Password fields: {web_features['password_fields']}, OTP fields: {web_features['otp_fields']}",
            })
        if web_features["external_form_action"]:
            evidence.append({"type": "webpage_indicator", "indicator": "external_form_action", "value": web_features["action_targets"]})
        if web_features["brand_impersonation"]:
            evidence.append({"type": "webpage_indicator", "indicator": "brand_impersonation", "value": web_features["claimed_brand"]})

    malicious_prob = calculate_malicious_probability(evidence)
    classification = "suspicious_indicators" if evidence else "no_lexical_indicators"

    limitations = [
        "Lexical indicators do not prove maliciousness.",
        "URL was not fetched or resolved.",
    ]
    if not html_content:
        limitations.append("Webpage DOM analysis was not performed (no HTML supplied).")

    elapsed = (time.perf_counter() - start) * 1000

    combined_features = {
        **f,
        "feature_version": URL_FEATURE_VERSION,
        "malicious_url_probability": malicious_prob,
        **({f"webpage_{k}": v for k, v in web_features.items()} if web_features else {}),
    }

    return DetectorResult(
        detector="url_lexical",
        detector_version=DETECTOR_VERSION,
        method="hybrid",
        classification=classification,
        confidence=malicious_prob,
        confidence_status="calibrated_heuristic",
        evidence=evidence,
        features=combined_features,
        limitations=limitations,
        processing_time_ms=elapsed,
    )

