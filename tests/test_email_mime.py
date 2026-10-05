from backend.service import _detectors_for
from detectors.message_context import infer_message_context


def test_multipart_email_uses_decoded_text_html_links_and_attachment_names():
    raw_message = (
        "From: Security Team <alerts@example.org>\r\n"
        "Subject: =?utf-8?q?Review_your_account?=\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/alternative; boundary="mail-boundary"\r\n'
        "\r\n"
        "--mail-boundary\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "Content-Transfer-Encoding: quoted-printable\r\n"
        "\r\n"
        "Please review the attached report.\r\n"
        "--mail-boundary\r\n"
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        '<p>Review your account <a href="https://paypa1-security.example/signin">'
        "https://paypal.example/signin</a></p>\r\n"
        "--mail-boundary\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="statement.pdf"\r\n'
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "JVBERi0xLjQ=\r\n"
        "--mail-boundary--\r\n"
    )

    detected = infer_message_context(raw_message)

    assert detected["subject"] == "Review your account"
    assert detected["message_text"] == "Please review the attached report."
    assert detected["links"] == [{
        "url": "https://paypa1-security.example/signin",
        "displayed_text": "https://paypal.example/signin",
    }]
    assert detected["attachment_names"] == ["statement.pdf"]
    assert detected["parser_warnings"] == []


def test_mime_hidden_link_reaches_url_detector_with_displayed_text():
    raw_message = (
        "From: Sender <sender@example.org>\n"
        "Subject: Document\n"
        "MIME-Version: 1.0\n"
        'Content-Type: text/html; charset="utf-8"\n'
        "\n"
        '<a href="https://paypa1-security.example/signin">'
        "https://paypal.example/signin</a>"
    )

    detector_results, details = _detectors_for({"type": "email", "raw_message": raw_message})
    url_result = next(item for item in detector_results if item["detector"] == "url_lexical")

    assert set(details["auto_detected"]["urls"]) == {
        "https://paypa1-security.example/signin",
        "https://paypal.example/signin",
    }
    assert "url_mismatch" in {item["indicator"] for item in url_result["evidence"]}


def test_pasted_authentication_results_are_displayed_but_not_trusted_as_evidence():
    detector_results, details = _detectors_for({
        "type": "email",
        "raw_message": (
            "From: Sender <sender@example.org>\n"
            "Authentication-Results: mx.example; spf=fail; dkim=fail; dmarc=fail\n\n"
            "The quarterly report is ready."
        ),
    })
    identity_result = next(
        item for item in detector_results if item["detector"] == "identity_impersonation"
    )

    assert details["auto_detected"]["authentication_as_pasted"] == {
        "spf": "fail",
        "dkim": "fail",
        "dmarc": "fail",
    }
    assert "domain_anomaly" not in {
        item["indicator"] for item in identity_result["evidence"]
    }
