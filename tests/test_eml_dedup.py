"""Unit tests for services/eml_dedup.py"""
import pytest
from services.eml_dedup import (
    deduplicate_contacts, _normalize_email, _normalize_phone,
    _name_similarity, _domain_from_email, _exact_key,
)


def _contact(name="", email="", phone="", company="", city=""):
    return {
        "name": name,
        "email_primary": email,
        "phone_primary": phone,
        "company": company,
        "city": city,
        "created_at": "2024-01-01",
    }


class TestNormalizeEmail:
    def test_lowercase(self):
        assert _normalize_email("John@Example.COM") == "john@example.com"

    def test_strips_whitespace(self):
        assert _normalize_email("  test@x.com  ") == "test@x.com"

    def test_empty(self):
        assert _normalize_email("") == ""

    def test_none(self):
        assert _normalize_email(None) == ""


class TestNormalizePhone:
    def test_strips_dashes(self):
        assert _normalize_phone("98765-43210") == "9876543210"

    def test_strips_country_code(self):
        assert _normalize_phone("+91 9876543210") == "9876543210"

    def test_strips_country_code_91(self):
        assert _normalize_phone("91 98765432101") == "98765432101"

    def test_empty(self):
        assert _normalize_phone("") == ""


class TestNameSimilarity:
    def test_identical(self):
        assert _name_similarity("John Smith", "John Smith") == 1.0

    def test_case_insensitive(self):
        assert _name_similarity("JOHN", "john") == 1.0

    def test_similar(self):
        assert _name_similarity("John Smith", "Jon Smith") > 0.85

    def test_different(self):
        assert _name_similarity("Alice", "Bob") < 0.5

    def test_empty(self):
        assert _name_similarity("", "John") == 0.0


class TestDomainFromEmail:
    def test_extracts(self):
        assert _domain_from_email("user@corp.com") == "corp.com"

    def test_empty(self):
        assert _domain_from_email("") == ""


class TestExactKey:
    def test_basic(self):
        c = _contact(name="John", email="j@x.com", phone="9876543210")
        key = _exact_key(c)
        assert "j@x.com" in key
        assert "john" in key

    def test_same_contacts_same_key(self):
        c1 = _contact(name="John", email="j@x.com", phone="9876543210")
        c2 = _contact(name="John", email="j@x.com", phone="9876543210")
        assert _exact_key(c1) == _exact_key(c2)


class TestDeduplicateContacts:
    def test_empty_input(self):
        unique, groups = deduplicate_contacts([])
        assert unique == []
        assert groups == []

    def test_exact_email_match(self):
        c1 = _contact(name="John Smith", email="john@corp.com", phone="111")
        c2 = _contact(name="John Smith", email="john@corp.com", phone="222")
        unique, groups = deduplicate_contacts([c1, c2])
        assert len(unique) == 1
        assert len(groups) == 1

    def test_exact_phone_match(self):
        c1 = _contact(name="John", email="a@b.com", phone="9876543210")
        c2 = _contact(name="John", email="a@b.com", phone="9876543210")
        unique, groups = deduplicate_contacts([c1, c2])
        assert len(unique) == 1

    def test_fuzzy_name_same_domain(self):
        c1 = _contact(name="John Smith", email="john@corp.com", phone="111")
        c2 = _contact(name="Jon Smith", email="jon@corp.com", phone="222")
        unique, groups = deduplicate_contacts([c1, c2])
        assert len(unique) == 1

    def test_different_people_no_dedup(self):
        c1 = _contact(name="Alice", email="alice@x.com", phone="111")
        c2 = _contact(name="Bob", email="bob@y.com", phone="222")
        unique, groups = deduplicate_contacts([c1, c2])
        assert len(unique) == 2
        assert len(groups) == 0

    def test_merge_fills_blanks(self):
        c1 = _contact(name="John", email="j@x.com", phone="", company="Acme")
        c2 = _contact(name="John", email="j@x.com", phone="12345", company="")
        unique, groups = deduplicate_contacts([c1, c2])
        assert len(unique) == 1
        merged = unique[0]
        assert merged["phone_primary"] == "12345"
        assert merged["company"] == "Acme"

    def test_keeps_newest(self):
        c_old = _contact(name="John", email="j@x.com", company="OldCo")
        c_old["created_at"] = "2024-01-01"
        c_new = _contact(name="John", email="j@x.com", company="NewCo")
        c_new["created_at"] = "2024-06-01"
        unique, _ = deduplicate_contacts([c_old, c_new])
        assert unique[0]["company"] == "NewCo"

    def test_multiple_groups(self):
        contacts = [
            _contact(name="Alice", email="a@x.com", phone="111"),
            _contact(name="Alice", email="a@x.com", phone="222"),
            _contact(name="Bob", email="b@y.com", phone="333"),
            _contact(name="Bob", email="b@y.com", phone="444"),
        ]
        unique, groups = deduplicate_contacts(contacts)
        assert len(unique) == 2
        assert len(groups) == 2
