"""Tests for EML export functions."""
from services.eml_export import export_csv, export_vcf, export_excel_data

SAMPLE_CONTACTS = [
    {"name": "John Smith", "email": "john@abc.com", "company": "ABC Corp",
     "designation": "Manager", "phone_primary": "9876543210",
     "confidence": 85, "extraction_method": "heuristic"},
    {"name": "Jane Doe", "email": "jane@xyz.com", "company": "XYZ Ltd",
     "designation": "Director", "phone_primary": "8765432109",
     "confidence": 90, "extraction_method": "deterministic"},
]


def test_csv_export():
    result = export_csv(SAMPLE_CONTACTS)
    assert "John Smith" in result
    assert "john@abc.com" in result
    assert "Jane Doe" in result
    assert "jane@xyz.com" in result


def test_vcf_export():
    result = export_vcf(SAMPLE_CONTACTS)
    assert "BEGIN:VCARD" in result
    assert "FN:John Smith" in result
    assert "EMAIL:john@abc.com" in result
    assert "END:VCARD" in result


def test_excel_data():
    data = export_excel_data(SAMPLE_CONTACTS)
    assert len(data["all_contacts"]) == 2
    assert len(data["unique_contacts"]) == 2
    assert len(data["domain_summary"]) == 2


def test_empty_export():
    assert export_csv([]) == ""
    assert export_vcf([]) == ""


def test_unique_contacts_deduplicates_by_email():
    contacts = [
        {"email": "dup@test.com", "name": "First"},
        {"email": "dup@test.com", "name": "Second"},
        {"email": "other@test.com", "name": "Third"},
    ]
    data = export_excel_data(contacts)
    assert len(data["unique_contacts"]) == 2
    assert data["unique_contacts"][0]["Name"] == "First"


def test_vcf_optional_fields():
    result = export_vcf([{"name": "Minimal"}])
    assert "BEGIN:VCARD" in result
    assert "FN:Minimal" in result
    assert "END:VCARD" in result
    assert "EMAIL" not in result
    assert "TEL" not in result
