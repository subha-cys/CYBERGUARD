"""Application service used by the local dashboard and actual detector pipeline."""
from __future__ import annotations

import base64
import json
import mimetypes
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.pipeline import analyze
from database.incidents import DEFAULT_DB, IncidentStore

ROOT = Path(__file__).resolve().parents[1]
PHISHING_MODEL = ROOT / "models/phishing/model.joblib"
LOGIN_MODEL = ROOT / "models/login/model.joblib"
DASHBOARD_DB = ROOT / "database/dashboard.sqlite3"


@lru_cache(maxsize=1)
def _phishing_detector():
    from detectors.phishing import PhishingNLPDetector
    return PhishingNLPDetector(PHISHING_MODEL)


@lru_cache(maxsize=1)
def _login_ml_detector():
    from detectors.login_ml import LoginIsolationForestDetector
    return LoginIsolationForestDetector(LOGIN_MODEL)


def _init_metrics():
    DASHBOARD_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DASHBOARD_DB) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS analyses (
            analysis_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            threat TEXT NOT NULL, severity TEXT NOT NULL, processing_ms REAL NOT NULL,
            detector_names TEXT NOT NULL, incident_id TEXT
        )""")


def _add_evidence_result(detector_result):
    return detector_result.to_dict()


def _detectors_for(payload: dict) -> tuple[list[dict], dict]:
    kind = payload.get("type", "email")
    details = {}
    from detectors.url import analyze_url
    from features.url import extract_urls

    if kind == "email" and "raw_message" in payload:
        from detectors.message_context import infer_message_context
        from detectors.phishing_rules import PhishingSecurityRulesDetector

        inferred = infer_message_context(payload.get("raw_message", ""))
        analysis_text = (
            f"Subject: {inferred['subject']}\n\n{inferred['message_text']}"
            if inferred["subject"] else inferred["message_text"]
        )
        if not analysis_text.strip():
            raise ValueError("pasted email must include a subject or message body")
        security_result = PhishingSecurityRulesDetector().analyze(
            analysis_text, inferred["sender_address"] or None
        )
        results = []
        phishing_model_available = PHISHING_MODEL.is_file()
        if phishing_model_available:
            results.append(_add_evidence_result(_phishing_detector().analyze(analysis_text)))
        results.append(_add_evidence_result(security_result))
        found_urls = list(dict.fromkeys([
            *extract_urls(analysis_text),
            *(link["url"] for link in inferred["links"]),
        ]))
        linked_display_text = {link["url"]: link["displayed_text"] for link in inferred["links"]}
        results.extend(
            _add_evidence_result(analyze_url(url, displayed_url=linked_display_text.get(url)))
            for url in found_urls
        )
        details = {
            "channel": "email" if inferred["format"] == "email_with_headers" else "message",
            "auto_detected": {
                "sender": inferred["sender_address"] or "Not present in message",
                "sender_domain": inferred["sender_domain"] or "Not detectable",
                "sender_organization": inferred["sender_domain_organization"] or "Not detectable",
                "display_name": inferred["display_name"] or "Not present in message",
                "subject": inferred["subject"] or "Not present",
                "format": inferred["format"],
                "claimed_role": inferred["claimed_role"] or "Not explicitly detected",
                "claimed_organization": inferred["claimed_organization"] or "Not explicitly detected",
                "objectives": inferred["objectives"],
                "urls": found_urls,
                "links": inferred["links"],
                "attachments": inferred["attachment_names"],
                "decoding_warnings": inferred["decoding_warnings"],
                "parser_warnings": inferred["parser_warnings"],
                "authentication_as_pasted": {
                    key: value for key, value in inferred["headers"].items()
                    if key in {"spf", "dkim", "dmarc"}
                },
                "phishing_model": "available" if phishing_model_available else "not installed",
                "identity_source": inferred["identity_source"],
                "role_source": inferred["role_source"],
                "organization_source": inferred["organization_source"],
            },
        }
    elif kind in {"email", "sms", "social_media", "qr_code"}:
        text = payload.get("text", "")
        explicit_url = payload.get("url")
        if not text and explicit_url:
            text = f"URL payload: {explicit_url}"
        if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
            raise ValueError(f"{kind} text or URL must contain 1 to 100,000 characters")

        from detectors.phishing_rules import PhishingSecurityRulesDetector
        nlp_res = _add_evidence_result(_phishing_detector().analyze(text))
        sec_res = _add_evidence_result(PhishingSecurityRulesDetector().analyze(text, payload.get("sender"), explicit_url))
        results = [nlp_res, sec_res]

        # Extract all URLs from message text plus any explicitly provided URL
        found_urls = extract_urls(text)
        if explicit_url and explicit_url not in found_urls:
            found_urls.append(explicit_url)

        for u in found_urls:
            results.append(_add_evidence_result(analyze_url(
                u,
                html_content=payload.get("html_content"),
                displayed_url=payload.get("displayed_url"),
                redirect_chain=payload.get("redirect_chain"),
            )))

        details = {
            "text": text,
            "sender": payload.get("sender"),
            "url": explicit_url,
            "extracted_urls": found_urls,
            "channel": kind,
        }
    elif kind in {"url", "website", "login_page"}:
        url = payload.get("url", "")
        html_content = payload.get("html_content") or payload.get("html")
        if not isinstance(url, str) or not url or len(url) > 8192:
            raise ValueError("URL must contain 1 to 8,192 characters")
        res = analyze_url(
            url,
            html_content=html_content,
            displayed_url=payload.get("displayed_url"),
            redirect_chain=payload.get("redirect_chain"),
        )
        results = [_add_evidence_result(res)]
        details = {
            "url": url,
            "has_html_content": bool(html_content),
            "displayed_url": payload.get("displayed_url"),
        }
    elif kind == "login":
        from detectors.login import analyze_login
        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("login event must be a JSON object")
        results = [_add_evidence_result(analyze_login(event)), _add_evidence_result(_login_ml_detector().analyze(event))]
        details = {"event": event}
    elif kind in {"image", "audio", "voice", "video", "video_call", "multimodal"}:
        from detectors.multimedia import analyze_audio, analyze_image, analyze_video
        normalized_kind = "audio" if kind == "voice" else ("video" if kind in {"video_call", "multimodal"} else kind)
        analyzer = {"image": analyze_image, "audio": analyze_audio, "video": analyze_video}[normalized_kind]

        if payload.get("path"):
            media_path = Path(payload["path"])
            if not media_path.is_file():
                raise ValueError(f"media path does not identify an existing file: {media_path}")
            raw_len = media_path.stat().st_size
            filename = payload.get("filename") or media_path.name
            result = analyzer(media_path)
            results = [_add_evidence_result(result)]
            details = {"media_type": kind, "filename": filename, "byte_length": raw_len}
        else:
            filename = str(payload.get("filename", "media.bin"))[:200]
            encoded = payload.get("content_base64")
            if not isinstance(encoded, str) or len(encoded) > 140_000_000:
                raise ValueError("media upload is missing or exceeds the 100 MiB limit")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError("media upload is not valid base64") from exc
            if not raw or len(raw) > 100 * 1024 * 1024:
                raise ValueError("media file must be between 1 byte and 100 MiB")
            suffix = Path(filename).suffix[:16]
            with tempfile.NamedTemporaryFile(prefix="cyberguard-upload-", suffix=suffix, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(raw)
            try:
                result = analyzer(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
            results = [_add_evidence_result(result)]
            details = {"media_type": kind, "filename": filename, "byte_length": len(raw)}
    else:
        raise ValueError("type must be email, sms, social_media, qr_code, url, website, login_page, login, image, audio, voice, video, or video_call")
    return results, details


def analyze_request(
    payload: dict,
    *,
    asset_sensitivity: str = "medium",
    persist_incident: bool = True,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    started = time.perf_counter()
    detector_results, input_details = _detectors_for(payload)
    result = analyze(detector_results, asset_sensitivity=asset_sensitivity)
    processing_ms = round((time.perf_counter() - started) * 1000, 3)

    # Compute top-level standard contract fields
    phishing_probs = [
        d["features"].get("phishing_probability", 0.90 if d["classification"] == "phishing" else 0.05)
        for d in detector_results if d["detector"] == "phishing_nlp"
    ]
    phishing_prob = phishing_probs[0] if phishing_probs else 0.0

    url_probs = [
        d["features"].get("malicious_url_probability", d.get("confidence", 0.02))
        for d in detector_results if d["detector"] == "url_lexical"
    ]
    malicious_url_prob = max(url_probs) if url_probs else 0.0

    # Multimedia authenticity contract fields
    media_results = [d for d in detector_results if d["detector"] == "multimedia_assessment"]
    if media_results:
        m_feat = media_results[0].get("features", {})
        result["authenticity_score"] = m_feat.get("authenticity_score", 1.0)
        result["manipulation_probability"] = m_feat.get("manipulation_probability", 0.0)
        result["confidence"] = m_feat.get("confidence", 0.80)
        result["detected_indicators"] = m_feat.get("detected_indicators", [])
        result["concern_level"] = m_feat.get("concern_level", "LOW CONCERN")
    else:
        result["authenticity_score"] = None
        result["manipulation_probability"] = None
        result["confidence"] = None
        result["detected_indicators"] = []
        result["concern_level"] = None

    result["processing_time_ms"] = processing_ms
    result["input"] = {"type": payload.get("type"), **input_details}
    synthetic_demo = not persist_incident and payload.get("synthetic_demo") is True
    if synthetic_demo:
        result["input"]["synthetic_demo"] = True
        result["input"]["scenario"] = str(payload.get("demo_id") or "prefilled synthetic scenario")
    result["phishing_probability"] = round(phishing_prob, 4)
    result["malicious_url_probability"] = round(malicious_url_prob, 4)
    result["risk_score"] = result["risk"]["risk_score"]
    result["risk_level"] = result["concern_level"] or result["risk"]["severity"].upper()
    result["threat_category"] = result["fusion"]["threat"]
    result["evidence"] = result["fusion"]["evidence"]
    result["recommended_action"] = [x["action"] for x in result["response"]]

    if persist_incident:
        auto_detected = input_details.get("auto_detected", {})
        input_summary = {"type": payload.get("type", "email")}
        sender = auto_detected.get("sender") or input_details.get("sender") or payload.get("sender")
        if sender and not str(sender).startswith("Not "):
            input_summary["sender"] = sender
        subject = auto_detected.get("subject")
        if subject and not str(subject).startswith("Not "):
            input_summary["subject"] = subject
        urls = auto_detected.get("urls") or input_details.get("extracted_urls") or []
        target = payload.get("url") or input_details.get("url")
        if target:
            input_summary["target"] = target
        if urls:
            input_summary["urls"] = urls
        if "filename" in input_details:
            input_summary["filename"] = input_details["filename"]
        result["incident"] = IncidentStore(DEFAULT_DB).create_if_required(
            result,
            source="live_analysis",
            input_summary=input_summary,
        )

    incident = result.get("incident")
    if persist_incident:
        _init_metrics()
        with sqlite3.connect(DASHBOARD_DB) as db:
            db.execute("INSERT INTO analyses(timestamp,threat,severity,processing_ms,detector_names,incident_id) VALUES (?,?,?,?,?,?)",
                       (result["created_at"], result["fusion"]["threat"], result["risk"]["severity"], processing_ms,
                        json.dumps([x["detector"] for x in detector_results]), incident.get("incident_id") if incident else None))
    return result


def demo_fixture_data(demo_id: str) -> dict:
    """Return a safe generated multimedia fixture for user-triggered analysis."""
    from datasets.media_fixtures import (
        create_manipulated_video_fixture,
        create_normal_audio_fixture,
        create_normal_image_fixture,
        create_normal_video_fixture,
        create_synthetic_audio_fixture,
        create_manipulated_image_fixture,
    )

    fixtures = {
        "normal_image": create_normal_image_fixture,
        "synthetic_manipulated_image": create_manipulated_image_fixture,
        "normal_audio": create_normal_audio_fixture,
        "synthetic_audio": create_synthetic_audio_fixture,
        "normal_video": create_normal_video_fixture,
        "manipulated_video": create_manipulated_video_fixture,
    }
    generator = fixtures.get(demo_id)
    if generator is None:
        raise ValueError("unknown synthetic media fixture")
    path = generator()
    content = path.read_bytes()
    if not content or len(content) > 100 * 1024 * 1024:
        raise ValueError("synthetic media fixture is empty or exceeds the analysis size limit")
    return {
        "filename": path.name,
        "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def set_incident_status(incident_id: str, status: str) -> dict:
    return IncidentStore(DEFAULT_DB).set_status(incident_id, status)


def dashboard_data() -> dict:
    _init_metrics()
    with sqlite3.connect(DASHBOARD_DB) as db:
        rows = db.execute("SELECT threat,severity,processing_ms FROM analyses").fetchall()
    incidents = IncidentStore(DEFAULT_DB).list(source="live_analysis")
    severity = {key: 0 for key in ("critical", "high", "medium", "low")}
    threats = {}
    for threat, level, _ in rows:
        severity[level] = severity.get(level, 0) + 1
        threats[threat] = threats.get(threat, 0) + 1
    active_incidents = [x for x in incidents if x["status"] not in {"resolved"}]
    detector_status = []
    for name, version, path in [
        ("Phishing NLP", "phishing-nlp-1.0.0", PHISHING_MODEL),
        ("Unified URL & Domain Analysis", "url-unified-2.0.0", None),
        ("Webpage DOM Security Analyzer", "webpage-dom-1.0.0", None),
        ("Phishing security rules", "security-text-2.0.0", None),
        ("Login anomaly rules", "login-rules-1.0.0", None),
        ("Login Isolation Forest", "login-iforest-1.0.0", LOGIN_MODEL),
        ("Multimedia metadata assessment", "multimedia-assessment-1.0.0", None),
    ]:
        detector_status.append({"name": name, "version": version,
                                "status": "ready" if path is None or path.is_file() else "model unavailable"})
    avg = sum(row[2] for row in rows) / len(rows) if rows else 0
    def registry_version(model_path: Path, default: str) -> str:
        registry = model_path.with_name("registry.json")
        try:
            return json.loads(registry.read_text(encoding="utf-8")).get("model_version", default)
        except (OSError, json.JSONDecodeError):
            return default
    return {"total_analyses": len(rows), "active_incidents": len(active_incidents),
            "severity_distribution": severity, "threat_categories": threats,
            "recent_incidents": incidents[:8], "average_processing_ms": round(avg, 2),
            "detector_status": detector_status,
            "model_versions": {"phishing": registry_version(PHISHING_MODEL, "unavailable") if PHISHING_MODEL.is_file() else "unavailable",
                               "login": registry_version(LOGIN_MODEL, "unavailable") if LOGIN_MODEL.is_file() else "unavailable"},
            "updated_at": datetime.now(timezone.utc).isoformat()}


def incident_data() -> list[dict]:
    return IncidentStore(DEFAULT_DB).list(source="live_analysis")
