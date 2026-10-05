"""Offline lexical and domain URL features. The input is never fetched or resolved."""
from __future__ import annotations

import ipaddress
import math
import re
from collections import Counter
from urllib.parse import unquote, urlsplit

URL_FEATURE_VERSION = "url-lexical-2.0.0"

SUSPICIOUS_TOKENS = {
    "login", "verify", "account", "secure", "update", "wallet",
    "password", "signin", "invoice", "banking", "authenticate",
    "confirm", "security", "support", "billing", "recovery", "helpdesk"
}

SUSPICIOUS_TLDS = {
    "xyz", "top", "work", "buzz", "club", "tk", "ml", "ga", "cf",
    "gq", "loan", "fit", "country", "click", "link", "rest", "cam",
    "kim", "surf", "icu", "monster", "cfd", "sbs", "quest"
}

POPULAR_BRANDS = [
    "google", "microsoft", "apple", "paypal", "amazon", "netflix",
    "chase", "bankofamerica", "wellsfargo", "facebook", "instagram",
    "twitter", "linkedin", "dropbox", "docusign", "yahoo", "outlook",
    "steam", "dhl", "fedex", "usps", "ups", "whatsapp", "telegram",
    "github", "adobe", "walmart", "ebay"
]

HOMOGLYPH_MAP = {
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    "0": "o", "1": "l", "3": "e", "5": "s", "@": "a", "$": "s"
}

URL_REGEX = re.compile(
    r"""(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))""",
    re.VERBOSE
)


def extract_urls(text: str) -> list[str]:
    """Safely extract all candidate URLs from a text body."""
    if not isinstance(text, str) or not text.strip():
        return []
    matches = URL_REGEX.findall(text)
    urls = []
    for match in matches:
        raw_url = match[0] if isinstance(match, tuple) else match
        cleaned = raw_url.strip(".,;:)'\"<>")
        if cleaned and cleaned not in urls:
            urls.append(cleaned)
    return urls


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def check_brand_similarity(host: str) -> dict:
    """Detect brand impersonation, typosquatting, or look-alike domains."""
    clean_host = host.lower().rstrip(".")
    labels = clean_host.split(".")
    main_part = labels[-2] if len(labels) >= 2 else labels[0]
    tokens = re.split(r"[-_.]", clean_host)
    
    # Check homoglyph translation
    normalized_main = "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in main_part)
    if normalized_main != main_part:
        for brand in POPULAR_BRANDS:
            if normalized_main == brand:
                return {
                    "is_lookalike": True,
                    "matched_brand": brand,
                    "similarity_score": 0.95,
                    "reason": f"Homoglyph character substitution targeting brand '{brand}'"
                }

    for brand in POPULAR_BRANDS:
        for t in tokens:
            norm_t = "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in t)
            if (t == brand or norm_t == brand) and not clean_host.endswith(f".{brand}.com") and clean_host != f"{brand}.com":
                return {
                    "is_lookalike": True,
                    "matched_brand": brand,
                    "similarity_score": 0.95 if norm_t != t else 0.90,
                    "reason": f"Brand name '{brand}' embedded in an unauthorized host/domain '{clean_host}'"
                }
            dist = _levenshtein(norm_t, brand)
            if 1 <= dist <= 2 and abs(len(norm_t) - len(brand)) <= 2 and len(brand) >= 4:
                ratio = 1.0 - (dist / max(len(norm_t), len(brand)))
                if ratio >= 0.70:
                    return {
                        "is_lookalike": True,
                        "matched_brand": brand,
                        "similarity_score": round(ratio, 2),
                        "reason": f"Domain token '{t}' resembles known brand '{brand}' (edit distance {dist})"
                    }

        dist = _levenshtein(normalized_main, brand)
        if 1 <= dist <= 2 and abs(len(normalized_main) - len(brand)) <= 2 and len(brand) >= 4:
            ratio = 1.0 - (dist / max(len(normalized_main), len(brand)))
            if ratio >= 0.70:
                return {
                    "is_lookalike": True,
                    "matched_brand": brand,
                    "similarity_score": round(ratio, 2),
                    "reason": f"Domain '{main_part}' resembles known brand '{brand}' (edit distance {dist})"
                }

    return {
        "is_lookalike": False,
        "matched_brand": None,
        "similarity_score": 0.0,
        "reason": None
    }


def detect_url_mismatch(displayed_text: str | None, destination_url: str | None) -> bool:
    """Check if displayed text claims to be a trusted URL but leads to a different host."""
    if not displayed_text or not destination_url:
        return False
    try:
        disp_cand = displayed_text.strip() if "://" in displayed_text else "http://" + displayed_text.strip()
        disp_host = (urlsplit(disp_cand).hostname or "").lower()
        dest_cand = destination_url.strip() if "://" in destination_url else "http://" + destination_url.strip()
        dest_host = (urlsplit(dest_cand).hostname or "").lower()
    except Exception:
        return False

    if not disp_host or not dest_host:
        return False
    if "." in disp_host and disp_host != dest_host and not dest_host.endswith("." + disp_host):
        return True
    return False


def extract_url_features(url: str) -> dict:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    value = url.strip()
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("url contains control characters")
    candidate = value if "://" in value else "http://" + value
    try:
        parts = urlsplit(candidate)
        host = parts.hostname or ""
    except ValueError as exc:
        raise ValueError("malformed URL") from exc
    if not host:
        raise ValueError("URL must include a hostname")
    try:
        ipaddress.ip_address(host.strip("[]"))
        ip_literal = True
    except ValueError:
        ip_literal = False

    labels = host.rstrip(".").split(".")
    tld = labels[-1].lower() if len(labels) > 1 and not ip_literal else ""
    suspicious_tld = tld in SUSPICIOUS_TLDS

    char_counts = Counter(value)
    entropy = -sum((n / len(value)) * math.log2(n / len(value)) for n in char_counts.values())
    decoded = unquote(value)
    tokens = sorted(t for t in SUSPICIOUS_TOKENS if t in decoded.lower())

    is_punycode = "xn--" in host.lower()
    has_homoglyphs = any(ch in HOMOGLYPH_MAP for ch in host.lower())

    brand_check = check_brand_similarity(host)

    has_non_standard_port = False
    if parts.port is not None:
        scheme = parts.scheme.lower()
        if (scheme == "http" and parts.port != 80) or (scheme == "https" and parts.port != 443):
            has_non_standard_port = True

    return {
        "url": value,
        "url_length": len(value),
        "subdomain_count": 0 if ip_literal else max(0, len(labels) - 2),
        "special_character_count": sum(not c.isalnum() for c in value),
        "suspicious_tokens": tokens,
        "ip_literal_host": ip_literal,
        "entropy_bits_per_character": round(entropy, 4),
        "encoded_character_count": len(re.findall(r"%[0-9a-fA-F]{2}", value)),
        "path_length": len(parts.path),
        "query_length": len(parts.query),
        "at_symbol_present": "@" in parts.netloc,
        "https_scheme": parts.scheme.lower() == "https",
        "hostname": host,
        "tld": tld,
        "suspicious_tld": suspicious_tld,
        "is_punycode": is_punycode,
        "has_homoglyphs": has_homoglyphs,
        "is_lookalike": brand_check["is_lookalike"],
        "matched_brand": brand_check["matched_brand"],
        "brand_similarity_score": brand_check["similarity_score"],
        "lookalike_reason": brand_check["reason"],
        "has_non_standard_port": has_non_standard_port,
        "domain_age_days": None,
    }
