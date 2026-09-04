"""Unit tests for services/eml_parser.py"""
import pytest
from services.eml_parser import parse_eml_bytes, _decode_header_value, _parse_address_list, _extract_text_from_html


SAMPLE_EML = b"""From: John Smith <john.smith@abcindustries.com>
To: sales@yourcompany.com
CC: manager@abcindustries.com
Subject: Partnership Inquiry
Date: Mon, 01 Jan 2024 10:30:00 +0530
Message-ID: <test123@abcindustries.com>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Dear Team,

We are interested in your products.

Regards,

John Smith
Senior Manager - Business Development

ABC Industries Pvt Ltd
Mobile: +91 98765 43210
Email: john.smith@abcindustries.com
Website: www.abcindustries.com
"""

SAMPLE_EML_HTML = b"""From: Jane Doe <jane@techcorp.com>
To: contact@vendor.com
Subject: Query
Date: Tue, 02 Jan 2024 14:00:00 +0530
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset="utf-8"

Hi,

Please share pricing.

--boundary123
Content-Type: text/html; charset="utf-8"

<html><body>
<p>Hi,</p>
<p>Please share pricing.</p>
<div class="gmail_signature">
<p>Regards,<br>Jane Doe<br>CTO<br>TechCorp Solutions</p>
</div>
</body></html>
--boundary123--
"""

SAMPLE_EML_MULTIPART = b"""From: Bob <bob@company.com>
To: alice@company.com
Subject: Report
Date: Wed, 03 Jan 2024 09:00:00 +0530
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="boundary456"

--boundary456
Content-Type: text/plain; charset="utf-8"

Please find attached report.

Bob Johnson
Director
--boundary456
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"

JVBERi0xLjQK
--boundary456--
"""


class TestParseEmlBytes:
    def test_simple_plain_text(self):
        result = parse_eml_bytes(SAMPLE_EML, "test.eml")
        assert result.file_name == "test.eml"
        assert result.from_name == "John Smith"
        assert result.from_email == "john.smith@abcindustries.com"
        assert result.subject == "Partnership Inquiry"
        assert "Dear Team" in result.body_text
        assert "John Smith" in result.body_text
        assert result.to_addrs[0]["email"] == "sales@yourcompany.com"
        assert result.cc_addrs[0]["email"] == "manager@abcindustries.com"
        assert result.html_body == ""

    def test_multipart_html(self):
        result = parse_eml_bytes(SAMPLE_EML_HTML, "html.eml")
        assert result.from_email == "jane@techcorp.com"
        assert "Hi" in result.body_text
        assert "gmail_signature" in result.html_body

    def test_multipart_mixed_with_attachment(self):
        result = parse_eml_bytes(SAMPLE_EML_MULTIPART, "report.eml")
        assert "report.pdf" in result.attachments
        assert "Bob Johnson" in result.body_text

    def test_empty_message(self):
        result = parse_eml_bytes(b"", "empty.eml")
        assert result.file_name == "empty.eml"
        assert result.body_text == ""
        assert result.from_email == ""

    def test_encoded_header(self):
        raw = b"From: =?UTF-8?Q?Rajesh_=C3=81nand?= <rajesh@test.com>\nSubject: Test\n\nBody"
        result = parse_eml_bytes(raw, "encoded.eml")
        assert "Rajesh" in result.from_name


class TestDecodeHeaderValue:
    def test_plain_ascii(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_none(self):
        assert _decode_header_value(None) == ""

    def test_empty(self):
        assert _decode_header_value("") == ""


class TestParseAddressList:
    def test_single_address(self):
        result = _parse_address_list("John <john@example.com>")
        assert len(result) == 1
        assert result[0]["email"] == "john@example.com"
        assert result[0]["name"] == "John"

    def test_multiple_addresses(self):
        result = _parse_address_list("a@test.com, b@test.com")
        assert len(result) == 2

    def test_empty(self):
        assert _parse_address_list("") == []


class TestExtractTextFromHtml:
    def test_strips_tags(self):
        assert _extract_text_from_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_strips_style_script(self):
        html = "<style>.x{color:red}</style><p>Text</p>"
        assert _extract_text_from_html(html) == "Text"

    def test_empty(self):
        assert _extract_text_from_html("") == ""
