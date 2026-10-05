"""Advisory-only response recommendations; no actions are executed."""


def recommend(fusion: dict, risk: dict) -> list[dict]:
    threat = fusion["threat"]
    indicators = {x.get("indicator") for x in fusion["evidence"]}
    actions = []
    if threat in {"phishing", "suspicious_phishing", "sms_phishing", "qr_phishing"}:
        actions.extend([
            ("quarantine_message", "Hold the message for analyst review to prevent user interaction."),
            ("warn_user", "Warn the recipient not to click links, open attachments, or submit credentials."),
            ("request_manual_verification", "Request manual verification of sender and message context from SOC analyst."),
        ])
        if "suspicious_url" in indicators or any(x["detector"] == "url_lexical" and x["normalized_signal"] == "support" for x in fusion["detector_results"]):
            actions.append(("block_url", "Submit the suspicious URL to edge gateways and DNS firewalls for blocking."))
        if "credential_request" in indicators or "otp_request" in indicators:
            actions.append(("assess_credential_exposure", "If credentials were entered, follow policy for session revocation and credential reset."))
    elif threat in {"malicious_url", "fake_login_page"}:
        actions.extend([
            ("block_url", "Block access to the malicious URL and associated domain across proxy and firewall."),
            ("warn_user", "Display a browser interstitial warning blocking navigation to the deceptive page."),
            ("request_manual_verification", "Request security analyst review and brand abuse takedown submission."),
        ])
    elif threat == "account_takeover":
        actions.extend([
            ("review_recent_login_history", "Review recent authentication activity and source device/IP."),
            ("revoke_sessions_if_compromise_confirmed", "If compromise is confirmed, revoke active sessions under analyst approval."),
            ("require_mfa_review", "Review MFA requirements for the affected account."),
            ("credential_reset_if_compromise_confirmed", "Reset credentials if the analyst confirms compromise."),
        ])
    elif threat == "multimedia_manipulation":
        actions.extend([
            ("preserve_evidence", "Preserve the original media and provenance/context for review."),
            ("verify_identity_independently", "Verify any identity claim through a known, independent contact channel."),
            ("escalate_analyst", "Escalate to a human analyst for review."),
        ])
    elif threat == "undetermined" and fusion["evidence"]:
        actions.append(("request_manual_verification", "Review the available indicators; the evidence is insufficient for a threat classification."))

    if risk.get("incident_required") and not any(x[0] == "flag_incident" for x in actions):
        actions.insert(0, ("flag_incident", f"Risk score ({risk.get('risk_score')}) crossed the incident threshold ({risk.get('incident_threshold')}); incident record logged."))

    if risk["severity"] in {"high", "critical"} and not any(x[0] in {"escalate_analyst", "request_manual_verification"} for x in actions):
        actions.append(("request_manual_verification", "Escalate for analyst review before taking response actions."))
    return [{"action": name, "rationale": rationale, "priority": "high" if risk["severity"] in {"high", "critical"} else "normal",
             "approval_required": True, "automatic_execution": False} for name, rationale in actions]
