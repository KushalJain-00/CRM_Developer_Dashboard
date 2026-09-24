# tests/test_eml_dedup_rules.py
from services.eml_dedup_rules import normalize_email, normalize_phone, is_duplicate

def test_normalize_email():
    assert normalize_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert normalize_email(None) == ""

def test_normalize_phone_keeps_digits():
    assert normalize_phone("+91 (98765) 43210") == "919876543210"
    assert normalize_phone(None) == ""

def test_dup_by_email():
    assert is_duplicate("a@b.com", None, {"a@b.com"}, set()) == "email"

def test_dup_by_phone_10_digits():
    # normalized phone compared as suffix/containment when >= 10 digits
    assert is_duplicate("x@y.com", "+91-98765-43210", set(), {"919876543210"}) == "phone"

def test_no_dup():
    assert is_duplicate("new@x.com", "9876543210", {"a@b.com"}, {"1111111111"}) is None

def test_short_phone_not_matched():
    assert is_duplicate("new@x.com", "12345", set(), {"12345"}) is None
