"""
Server-side EML parsing using Python's email stdlib.
Replaces client-side JS MIME parsing for the enterprise pipeline.
"""
import email
import email.policy
import email.utils
import re
import base64
from email import policy
from email.parser import BytesParser
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedEml:
    file_name: str
    subject: str
    date: str
    message_id: str
    from_name: str
    from_email: str
    to_addrs: list
    cc_addrs: list
    bcc_addrs: list
    reply_to: list
    body_text: str
    html_body: str
    attachments: list
    images: list
    headers: dict


def _decode_header_value(raw: Optional[str]) -> str:
    """Decode RFC 2047 encoded header value to string."""
    if not raw:
        return ""
    decoded_parts = email.header.decode_header(raw)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _parse_address_list(raw: str) -> list:
    """Parse comma-separated address string into [{name, email}]."""
    if not raw:
        return []
    addresses = email.utils.getaddresses([raw])
    return [{"name": name, "email": addr} for name, addr in addresses if addr]


def _extract_text_from_html(html: str) -> str:
    """Strip HTML tags to get plain text. Simple stdlib approach."""
    if not html:
        return ""
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:p|div|tr|li|td|th|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _find_inline_images(msg) -> list:
    """Extract inline image attachments as raw bytes."""
    images = []
    if not msg.is_multipart():
        return images
    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))
        if content_type and content_type.startswith("image/"):
            if "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    images.append(payload)
    return images


def _find_attachments(msg) -> list:
    """Extract attachment filenames."""
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        if "attachment" in content_disposition:
            filename = part.get_filename()
            if filename:
                attachments.append(filename)
    return attachments


def _extract_body_parts(msg) -> tuple:
    """Extract text/plain and text/html body parts from message."""
    body_text = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            if content_type and content_type.startswith("image/"):
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")

            if content_type == "text/plain" and not body_text:
                body_text = text
            elif content_type == "text/html" and not html_body:
                html_body = text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")

            if msg.get_content_type() == "text/html":
                html_body = text
                body_text = _extract_text_from_html(text)
            else:
                body_text = text

    if html_body and not body_text:
        body_text = _extract_text_from_html(html_body)

    return body_text, html_body


def parse_eml_bytes(raw_bytes: bytes, file_name: str = "unknown.eml") -> ParsedEml:
    """Parse raw .eml bytes into a ParsedEml dataclass."""
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    from_header = _decode_header_value(msg.get("From", ""))
    from_name, from_addr = email.utils.parseaddr(from_header)

    subject = _decode_header_value(msg.get("Subject", ""))
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "")

    to_addrs = _parse_address_list(msg.get("To", ""))
    cc_addrs = _parse_address_list(msg.get("CC", ""))
    bcc_addrs = _parse_address_list(msg.get("BCC", ""))
    reply_to = _parse_address_list(msg.get("Reply-To", ""))

    body_text, html_body = _extract_body_parts(msg)

    if len(body_text) > 50000:
        body_text = body_text[-50000:]
    if len(html_body) > 50000:
        html_body = html_body[-50000:]

    attachments = _find_attachments(msg)
    images = _find_inline_images(msg)

    headers = {}
    for key, val in msg.items():
        headers[key] = _decode_header_value(val)

    return ParsedEml(
        file_name=file_name,
        subject=subject,
        date=date_str,
        message_id=message_id,
        from_name=from_name or "",
        from_email=from_addr or "",
        to_addrs=to_addrs,
        cc_addrs=cc_addrs,
        bcc_addrs=bcc_addrs,
        reply_to=reply_to,
        body_text=body_text,
        html_body=html_body,
        attachments=attachments,
        images=images,
        headers=headers,
    )
