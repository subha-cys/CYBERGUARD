"""Safe offline HTML and webpage metadata feature extraction.

Does not actively crawl dangerous sites. Analyzes provided HTML or safe DOM snapshots.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

WEBPAGE_FEATURE_VERSION = "webpage-dom-1.0.0"

CREDENTIAL_INPUT_NAMES = {
    "password", "pass", "pwd", "userpass", "passwd", "pin", "otp",
    "token", "secret", "cvv", "cvc", "creditcard", "cardnumber",
    "ssn", "socialsecurity", "mfa_code", "authcode", "accesscode"
}

LOGIN_TOKENS = {
    "login", "sign in", "signin", "log in", "authenticate", "verify identity",
    "enter credentials", "account verification", "security check", "unlock account"
}

KNOWN_BRANDS = [
    ("microsoft", ["microsoft", "office 365", "outlook", "onedrive", "azure", "live.com"]),
    ("google", ["google", "gmail", "workspace", "google drive"]),
    ("apple", ["apple", "icloud", "apple id"]),
    ("paypal", ["paypal"]),
    ("amazon", ["amazon", "aws"]),
    ("netflix", ["netflix"]),
    ("chase", ["chase", "jpmorgan"]),
    ("bank of america", ["bank of america", "bofa"]),
    ("wells fargo", ["wells fargo"]),
    ("docusign", ["docusign"]),
    ("dropbox", ["dropbox"]),
    ("facebook", ["facebook", "meta"]),
]


def extract_webpage_features(html_content: str, page_url: str | None = None) -> dict:
    """Safely inspect HTML structure, metadata, forms, inputs, and brand claims."""
    if not isinstance(html_content, str):
        raise TypeError("html_content must be a string")

    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Title and text content
    title = (soup.title.string.strip() if soup.title and soup.title.string else "").lower()
    page_text = soup.get_text(separator=" ", strip=True).lower()

    # Form and input analysis
    forms = soup.find_all("form")
    has_form = len(forms) > 0

    all_inputs = soup.find_all("input")
    password_fields = 0
    otp_fields = 0
    text_credential_fields = 0
    hidden_fields = 0

    for inp in all_inputs:
        itype = (inp.get("type") or "text").lower()
        iname = (inp.get("name") or "").lower()
        iid = (inp.get("id") or "").lower()
        placeholder = (inp.get("placeholder") or "").lower()
        combined_id = f"{iname} {iid} {placeholder}"

        if itype == "password":
            password_fields += 1
        elif itype == "hidden":
            hidden_fields += 1

        if any(tok in combined_id for tok in ["otp", "pin", "token", "2fa", "code", "mfa"]):
            otp_fields += 1
        elif any(tok in combined_id for tok in CREDENTIAL_INPUT_NAMES):
            text_credential_fields += 1

    total_credential_fields = password_fields + otp_fields + text_credential_fields

    # External form action check
    page_host = ""
    if page_url:
        try:
            cand = page_url if "://" in page_url else "http://" + page_url
            page_host = (urlsplit(cand).hostname or "").lower()
        except Exception:
            page_host = ""

    external_form_action = False
    action_targets = []
    for form in forms:
        action = form.get("action", "").strip()
        if action:
            action_targets.append(action)
            if "://" in action or action.startswith("//"):
                try:
                    action_host = (urlsplit(action if "://" in action else "http:" + action).hostname or "").lower()
                    if page_host and action_host and action_host != page_host and not action_host.endswith("." + page_host):
                        external_form_action = True
                except Exception:
                    pass

    # Login-form presence
    has_login_form = (
        (password_fields > 0)
        or (has_form and any(tok in page_text for tok in LOGIN_TOKENS) and total_credential_fields > 0)
        or (has_form and "login" in "".join(action_targets).lower())
    )

    # Brand impersonation check
    claimed_brand = None
    brand_impersonated = False
    for brand_key, keywords in KNOWN_BRANDS:
        # If title or prominent heading mentions the brand
        if any(kw in title for kw in keywords) or any(kw in page_text[:500] for kw in keywords):
            # Check if current host belongs to that brand
            if page_host:
                is_legit = page_host == f"{brand_key}.com" or page_host.endswith(f".{brand_key}.com")
                if not is_legit:
                    claimed_brand = brand_key
                    brand_impersonated = True
                    break
            else:
                claimed_brand = brand_key

    # Fake login page assessment
    is_fake_login_page = has_login_form and (brand_impersonated or external_form_action or (page_host and "192.0.2." in page_host))

    # Evasion scripts / suspicious DOM indicators
    scripts = soup.find_all("script")
    script_text = " ".join(s.get_text() for s in scripts).lower()
    has_anti_analysis = any(tok in script_text for tok in ["contextmenu", "event.button==2", "debugger", "eval(", "unescape("])
    has_iframes = len(soup.find_all("iframe")) > 0

    return {
        "webpage_feature_version": WEBPAGE_FEATURE_VERSION,
        "title": title[:200],
        "has_form": has_form,
        "form_count": len(forms),
        "has_login_form": has_login_form,
        "password_fields": password_fields,
        "otp_fields": otp_fields,
        "credential_field_presence": total_credential_fields > 0,
        "total_credential_fields": total_credential_fields,
        "external_form_action": external_form_action,
        "action_targets": action_targets[:5],
        "claimed_brand": claimed_brand,
        "brand_impersonation": brand_impersonated,
        "is_fake_login_page": is_fake_login_page,
        "has_anti_analysis_scripts": has_anti_analysis,
        "has_iframes": has_iframes,
        "html_character_count": len(html_content),
    }

