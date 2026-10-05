"""Extract explicitly available sender metadata and cautious message-intent hints."""
from __future__ import annotations

import re
from email import policy
from email.parser import Parser
from email.utils import parseaddr

from bs4 import BeautifulSoup

_ROLE_PATTERNS = (
    ("government official", r"\b(?:government|ministry|municipal|public service)\s+official\b"),
    ("executive", r"\b(?:chief executive|ceo|cfo|cto|coo|chief operating officer|chief financial officer|chief technology officer|president|vice president)\b"),
    ("manager", r"\b(?:manager|supervisor|director|team lead|head of (?:department|team|operations))\b"),
    ("bank representative", r"\b(?:bank|banking)\s+(?:representative|officer|security team|manager)\b"),
    ("law enforcement", r"\b(?:police officer|law enforcement|detective|sheriff)\b"),
    ("IT support", r"\b(?:it support|help ?desk|system administrator|security team|technical support)\b"),
    ("professor", r"\b(?:professor|lecturer|teacher|instructor|faculty)\b"),
    ("human resources", r"\b(?:human resources|hr manager|recruiter)\b"),
)
_ORGANIZATION_PATTERNS = (
    re.compile(r"\b(?:from|at|with|representing|on behalf of)\s+(?:the\s+)?([A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*){0,3}(?:\.)?)"),
    re.compile(r"\b(?:your|our)\s+(bank|university|employer|government|company)\b", re.IGNORECASE),
)
_PERSONAL_MAIL_PROVIDERS = {
    "gmail.com": "Gmail",
    "yahoo.com": "Yahoo Mail",
    "outlook.com": "Outlook",
    "hotmail.com": "Hotmail",
    "proton.me": "Proton Mail",
    "protonmail.com": "Proton Mail",
    "icloud.com": "iCloud Mail",
    "aol.com": "AOL Mail",
    "mail.com": "Mail.com",
}
_OBJECTIVE_PATTERNS = (
    ("credential_or_otp_request", r"\b(?:otp|one[- ]time (?:password|code)|password|passcode|verification code|pin|cvv|login credentials)\b"),
    ("financial_action_or_payment", r"\b(?:transfer|wire|payment|pay|invoice|bank details|gift cards?|crypto|processing fee|funds)\b"),
    ("open_link_or_visit_site", r"https?://|www\.|\b(?:click|open|visit|follow)\s+(?:the\s+)?(?:link|url|website)\b"),
    ("download_or_open_attachment", r"\b(?:download|open|enable macros?|view)\s+(?:the\s+)?(?:attachment|file|document)\b"),
    ("share_sensitive_information", r"\b(?:send|share|provide|confirm)\s+(?:me\s+)?(?:your\s+)?(?:personal|confidential|account|customer|employee)\s+(?:information|data|details)\b"),
    ("keep_request_secret", r"\b(?:do not tell|don't tell|keep (?:this|it) secret|between us)\b"),
    ("urgent_response_requested", r"\b(?:urgent|immediately|right now|asap|before (?:the )?deadline|within \d+ hours?)\b"),
    ("account_access_or_verification", r"\b(?:verify|confirm|unlock|restore|suspend(?:ed)?|block(?:ed)?|secure)\s+(?:your\s+)?(?:account|access|identity|mailbox)\b"),
    ("request_for_documents_or_information", r"\b(?:send|share|provide|forward|submit|upload)\s+(?:me\s+)?(?:the\s+)?(?:document|file|report|information|details|records)\b"),
    ("meeting_or_callback", r"\b(?:schedule|book|join|attend)\s+(?:a\s+)?(?:meeting|call|appointment)\b|\bcall me back\b"),
    ("change_or_cancel_request", r"\b(?:cancel|delete|change|update|reset)\s+(?:your\s+)?(?:account|password|subscription|booking|details)\b"),
)


def infer_message_context(raw_message: str) -> dict:
    """Parse pasted RFC-style headers when present; never invent a sender or identity claim."""
    if not isinstance(raw_message, str) or not raw_message.strip() or len(raw_message) > 100_000:
        raise ValueError("message must contain 1 to 100,000 characters")

    normalized = raw_message.replace("\r\n", "\n").replace("\r", "\n")
    header_block, separator, body = normalized.partition("\n\n")
    parsed_headers = Parser(policy=policy.default).parsestr(header_block, headersonly=True)
    has_email_headers = any(parsed_headers.get(key) for key in ("From", "Subject", "Date", "Reply-To"))
    message = Parser(policy=policy.default).parsestr(normalized) if has_email_headers and separator else parsed_headers
    text = raw_message.strip()
    links = []
    attachment_names = []
    decoding_warnings = []
    parser_warnings = []
    if has_email_headers and separator:
        plain_parts = []
        html_parts = []
        for part in message.walk():
            parser_warnings.extend(
                f"Parser reported {type(defect).__name__}."
                for defect in part.defects
            )
            if part.is_multipart():
                continue
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if disposition == "attachment" or filename:
                if filename:
                    attachment_names.append(str(filename))
                continue
            if part.get_content_maintype() != "text":
                continue
            content_bytes = part.get_payload(decode=True)
            if content_bytes is None:
                content = part.get_content()
            else:
                charset = part.get_content_charset()
                if charset is None:
                    charset = "ascii" if content_bytes.isascii() else "utf-8"
                    if not content_bytes.isascii():
                        decoding_warnings.append("Text part omitted its charset; UTF-8 was assumed.")
                try:
                    content = content_bytes.decode(charset, errors="replace")
                except LookupError:
                    content = content_bytes.decode("utf-8", errors="replace")
                    decoding_warnings.append(f"Unsupported charset {charset!r}; decoded using UTF-8 replacement.")
                if "\ufffd" in content:
                    decoding_warnings.append(f"Text part using charset {charset!r} contains undecodable bytes.")
            if not isinstance(content, str):
                continue
            if part.get_content_subtype() == "plain":
                plain_parts.append(content.strip())
            elif part.get_content_subtype() == "html":
                soup = BeautifulSoup(content, "html.parser")
                html_parts.append(soup.get_text(separator=" ", strip=True))
                for anchor in soup.find_all("a", href=True):
                    destination = str(anchor.get("href", "")).strip()
                    if destination.lower().startswith(("http://", "https://", "www.")):
                        link = {
                            "url": destination,
                            "displayed_text": anchor.get_text(" ", strip=True),
                        }
                        if link not in links:
                            links.append(link)
        text_parts = plain_parts or html_parts
        text = "\n".join(part for part in text_parts if part).strip() or body.strip()
    from_header = str(parsed_headers.get("From", "")) if has_email_headers else ""
    sender_display, sender_address = parseaddr(from_header)
    sender_address = sender_address.strip().lower()
    sender_domain = sender_address.rsplit("@", 1)[-1] if "@" in sender_address else ""
    domain_labels = sender_domain.split(".") if sender_domain else []
    sender_domain_organization = domain_labels[-3] if len(domain_labels) >= 3 and domain_labels[-2] in {"co", "com", "org", "net", "gov", "edu"} else domain_labels[-2] if len(domain_labels) >= 2 else ""
    if sender_domain in _PERSONAL_MAIL_PROVIDERS:
        sender_domain_organization = f"{_PERSONAL_MAIL_PROVIDERS[sender_domain]} (personal email provider)"

    headers = {}
    if has_email_headers:
        for source, target in (("Reply-To", "reply-to"), ("Return-Path", "return-path"), ("Message-ID", "message-id")):
            value = parsed_headers.get(source)
            if value:
                headers[target] = value
        auth_results = " ".join(parsed_headers.get_all("Authentication-Results", []))
        for mechanism in ("spf", "dkim", "dmarc"):
            match = re.search(rf"\b{mechanism}\s*=\s*(pass|fail|softfail|permerror|none|neutral|temperror)\b", auth_results, re.I)
            if match:
                headers[mechanism] = match.group(1).lower()

    searchable = f"{sender_display}\n{parsed_headers.get('Subject', '') if has_email_headers else ''}\n{text}"
    role = next((name for name, pattern in _ROLE_PATTERNS if re.search(pattern, searchable, re.I)), "")
    organization = ""
    for pattern in _ORGANIZATION_PATTERNS:
        match = pattern.search(searchable)
        if match:
            organization = match.group(1).strip(" .,'\"")
            break

    objectives = [name for name, pattern in _OBJECTIVE_PATTERNS if re.search(pattern, searchable, re.I)]
    if not objectives:
        objectives = ["no_specific_action_detected"]

    subject = str(parsed_headers.get("Subject", "")).strip() if has_email_headers else ""
    return {
        "message_text": text,
        "sender_address": sender_address,
        "sender_domain": sender_domain,
        "sender_domain_organization": sender_domain_organization.replace("-", " ").title(),
        "display_name": sender_display.strip(),
        "headers": headers,
        "subject": subject,
        "format": "email_with_headers" if has_email_headers else "message_text",
        "claimed_role": role,
        "claimed_organization": organization,
        "objectives": objectives,
        "links": links,
        "attachment_names": attachment_names,
        "decoding_warnings": decoding_warnings,
        "parser_warnings": list(dict.fromkeys(parser_warnings)),
        "identity_source": "From header" if sender_address else "not present in pasted message",
        "role_source": "matched message wording" if role else "not explicitly detected",
        "organization_source": "matched message wording" if organization else "not explicitly detected",
    }
