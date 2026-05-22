"""
Unit tests for services/parser.py
"""
import pytest
from services.parser import parse_pdf, parse_xls, _extract_contacts_from_text, _dedupe_headers


class TestDedupeHeaders:
    def test_no_duplicates(self):
        result = _dedupe_headers(["Name", "Email", "Phone"])
        assert result == ["Name", "Email", "Phone"]

    def test_with_duplicates(self):
        result = _dedupe_headers(["Phone", "Phone", "Email"])
        assert result == ["Phone", "Phone_1", "Email"]

    def test_with_none(self):
        result = _dedupe_headers([None, "Email", None])
        assert result == ["Unnamed", "Email", "Unnamed_1"]


class TestExtractContactsFromText:
    def test_extracts_phones(self):
        text = """
        Patel Industries
        9876543210
        info@patel.com
        """
        rows = _extract_contacts_from_text(text)
        assert len(rows) >= 1
        # Should find at least one phone or email
        has_contact_info = any(
            r.get("Phone") or r.get("Email") for r in rows
        )
        assert has_contact_info

    def test_empty_text(self):
        result = _extract_contacts_from_text("")
        assert result == []

    def test_extracts_email(self):
        text = "Contact us at sales@example.com for more details."
        rows = _extract_contacts_from_text(text)
        assert len(rows) >= 1
        emails = [r.get("Email") for r in rows if r.get("Email")]
        assert "sales@example.com" in emails

    def test_multiple_contacts(self):
        text = """
        1. Ramesh Shah
        9876543210
        ramesh@shah.com

        2. Suresh Patel
        8765432109
        suresh@patel.com

        3. Mukesh Jain
        7654321098
        mukesh@jain.com
        """
        rows = _extract_contacts_from_text(text)
        assert len(rows) >= 3
