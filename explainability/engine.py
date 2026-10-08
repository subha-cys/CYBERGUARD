"""Deterministic explanations assembled only from structured analysis data."""


def explain(fusion: dict, risk: dict, recommendations: list[dict]) -> dict:
    threat = fusion["threat"]
    what = {
        "phishing": "The email analysis produced a phishing assessment.",
        "suspicious_phishing": "The email analysis found phishing indicators without a positive NLP classification.",
        "account_takeover": "The login analysis produced account takeover risk indicators.",
        "multimedia_manipulation": "The media assessment produced manipulation indicators; this does not alone establish a deepfake or identify who is depicted.",
        "synthetic_voice": "Acoustic heuristics flagged this recording as likely AI-generated; this is not a validated model verdict.",
        "identity_impersonation": "Contextual security rules raised an identity impersonation concern; this does not establish that the media itself is manipulated.",
        "benign": "The phishing text model classified the message as benign, with no conflicting detector signal.",
        "no_threat_detected": "The login detectors reported no anomaly for the supplied event.",
        "undetermined": "Available detector outputs did not establish a threat classification.",
    }.get(threat, "The analysis produced a threat assessment.")
    why = []
    actual_conflicts = {name for category in fusion["categories"].values() for name in category["conflicting_detectors"]}
    for detector in fusion["detector_results"]:
        if detector["normalized_signal"] == "support":
            why.append(f"{detector['detector']} ({detector['detector_version']}) reported {detector['classification']}.")
        elif detector["normalized_signal"] == "conflict" and detector["detector"] in actual_conflicts:
            why.append(f"{detector['detector']} ({detector['detector_version']}) reported {detector['classification']}, which conflicts with other indicators.")
        if detector.get("voice_origin_signal") == "support":
            why.append(f"{detector['detector']} flagged the voice as likely AI-generated using acoustic heuristics.")
        elif detector.get("voice_origin_signal") == "conflict" and detector["detector"] in actual_conflicts:
            why.append(f"{detector['detector']} assessed the voice as likely human, conflicting with other voice-origin indicators.")
    if not why and threat in {"benign", "no_threat_detected"}:
        why.append("No detector reported a positive threat signal.")
    evidence = [{"detector": x["detector"], "indicator": x.get("indicator"), "type": x.get("type"),
                 "value": x.get("value")} for x in fusion["evidence"]]
    confidences = [{"detector": x["detector"], "confidence": x["confidence"],
                    "status": x["confidence_status"]} for x in fusion["detector_results"]]
    risk_reasons = [f"{x['factor']}: +{x['points']} ({x['reason']})" for x in risk["contributors"]]
    limitations = list(dict.fromkeys(lim for x in fusion["detector_results"] for lim in x["limitations"]))
    # Human-readable reasons corresponding to specific observed indicators
    reason_map = {
        "lookalike_domain": "Domain resembles a known organization or popular brand.",
        "identity_claim_inconsistent": "Sender address or account details do not match the claimed identity or organization.",
        "abnormal_context": "Sender or communication context differs from the configured baseline.",
        "independent_verification_absent": "No prior sender-recipient interaction is recorded; verify the request independently.",
        "urgency": "Message creates urgency or threatens account suspension.",
        "fake_login_page": "Page mimics a branded login interface on an unauthorized domain.",
        "login_form_present": "Page contains a credential-login form.",
        "credential_fields_present": "Page contains credential or password input fields.",
        "external_form_action": "Login form posts submitted credentials to an external or unrelated domain.",
        "credential_request": "Message requests sensitive credentials, passwords, or account verification.",
        "otp_request": "Message requests one-time password (OTP) or two-factor authentication code.",
        "ip_literal_host": "URL uses an IP address instead of a legitimate registered domain name.",
        "homoglyph_domain": "Domain contains deceptive look-alike or homoglyph characters.",
        "url_mismatch": "Destination URL differs from the displayed link text.",
        "excessive_redirects": "URL undergoes excessive redirects across unrelated domains.",
        "suspicious_tld": "Domain uses a top-level domain frequently associated with spam and abuse.",
        "smishing_indicators": "Message exhibits SMS phishing (smishing) lure characteristics.",
        "quishing_indicators": "Message instructs user to scan an unverified QR code (quishing).",
        "impersonation_language": "Message uses executive or institutional impersonation language.",
        "long_url": "URL is unusually long and contains excessive path or encoded parameters.",
        "encoded_characters": "URL contains multiple hex-encoded characters to obfuscate destination.",
        "many_subdomains": "URL contains an excessive number of subdomains.",
        "at_symbol_in_authority": "URL uses the '@' character to deceive destination parsing.",
        "spectral_grid_artifacts": "Periodic high-frequency spectral spikes characteristic of generative model upsampling (e.g., GAN or Diffusion deconvolution).",
        "compression_inconsistency_ela": "Error Level Analysis (ELA) detected significant compression discrepancy between image regions, indicating splicing or composition.",
        "noise_residual_inconsistency": "Inconsistent camera sensor noise (PRNU) variance observed across image spatial quadrants.",
        "blending_seam_detected": "Unnatural gradient sharpness and edge seams detected around localized foreground boundaries.",
        "synthetic_vocoder_cutoff": "Sharp brick-wall frequency cutoff detected in audio, characteristic of neural vocoder speech synthesis.",
        "manipulation_model_indicator": "The evaluated local media model reported a synthetic-class score above its validation-selected threshold; the score is uncalibrated.",
        "voice_origin_assessment": "Acoustic heuristic assessment of whether the voice is likely AI-generated, likely human, or inconclusive.",
        "low_vocal_microvariation": "Vocal track lacks natural biological micro-jitter and shimmer, displaying mechanical periodicity.",
        "robotic_pitch_stability": "Vocal pitch exhibits unnatural robotic flatness lacking human prosodic variation.",
        "unnatural_silence_dropout": "Audio contains artificial digital zero-energy dropouts rather than natural room acoustic ambiance.",
        "temporal_frame_discontinuity": "Sudden frame-to-frame structural similarity (SSIM) drop detected, indicating spliced or swapped video frames.",
        "optical_flow_jitter": "Irregular optical flow velocity variance detected, suggesting facial boundary warping or temporal swimming.",
        "luminance_temporal_flicker": "Abnormal frame-to-frame exposure or color temperature flickering observed in video.",
        "keyframe_visual_anomaly": "Sampled video keyframes exhibit compression or generative frequency artifacts.",
    }

    observed_reasons = []
    seen_indicators = set()
    for ev in fusion.get("evidence", []):
        ind = ev.get("indicator")
        if ind and ind in reason_map and ind not in seen_indicators:
            observed_reasons.append(reason_map[ind])
            seen_indicators.add(ind)

    if not observed_reasons and why:
        observed_reasons = why[:]

    return {
        "what": what, "why": why, "reasons": observed_reasons, "evidence": evidence, "model_confidence": confidences,
        "risk": {"score": risk["risk_score"], "severity": risk["severity"], "contributors": risk_reasons},
        "limitations": limitations, "recommended_action": [x["action"] for x in recommendations],
        "source": "detector evidence, fusion decisions, risk contributors, and response policy only",
    }
