"""
Unit tests for services/eml_signature.py
"""
import pytest
from services.eml_signature import extract_signature


class TestFullSignature:
    def test_all_fields_present(self):
        body = (
            "Hello,\n\n"
            "Please find the report attached.\n\n"
            "--\n"
            "Rajesh Kumar\n"
            "Managing Director\n"
            "Patel Industries Pvt Ltd\n"
            "Phone: +91 9876543210\n"
            "www.patelindustries.com\n"
            "Mumbai, Maharashtra 400001\n"
            "123 MG Road, Andheri East\n"
        )
        r = extract_signature(body, None, 'Rajesh Kumar', 'rajesh@patelindustries.com')
        assert r['name'] == 'Rajesh Kumar'
        assert r['email'] == 'rajesh@patelindustries.com'
        assert r['phone_primary'] is not None
        assert r['company'] is not None
        assert r['designation'] is not None
        assert r['confidence'] >= 60

    def test_minimal_body(self):
        body = "Thanks,\nJohn\njohn@example.com\n9876543210"
        r = extract_signature(body, None, 'John', 'john@example.com')
        assert r['name'] == 'John'
        assert r['email'] == 'john@example.com'
        assert r['phone_primary'] is not None
        assert r['confidence'] >= 40

    def test_empty_body(self):
        r = extract_signature('', None, '', '')
        assert r['name'] is None
        assert r['email'] is None
        assert r['confidence'] == 0

    def test_none_body(self):
        r = extract_signature(None, None, None, None)
        assert r['confidence'] == 0


class TestPhoneExtraction:
    def test_indian_mobile(self):
        body = "Call me at 9876543210\nRegards"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['phone_primary'] == '9876543210'

    def test_international_phone(self):
        body = "Call me at +1 5551234567\nThanks"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        # Space stripped during cleaning — matches regex output
        assert r['phone_primary'] == '+15551234567'

    def test_two_phones(self):
        body = "--\nRajesh Kumar\n9876543210\n8765432109\nAcme Corp"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['phone_primary'] == '9876543210'
        assert r['phone_secondary'] == '8765432109'

    def test_no_phones(self):
        body = "Hello\nBest regards"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['phone_primary'] is None
        assert r['phone_secondary'] is None


class TestCompanyExtraction:
    def test_company_from_signature(self):
        body = "Rajesh\nDirector\nPatel Industries Pvt Ltd\nMumbai"
        r = extract_signature(body, None, 'Rajesh', 'rajesh@patelindustries.com')
        assert r['company'] is not None
        assert 'patel' in r['company'].lower() or 'industries' in r['company'].lower()

    def test_company_from_domain(self):
        body = "Regards\nRajesh"
        r = extract_signature(body, None, 'Rajesh', 'rajesh@tataconsultancy.com')
        assert r['company'] == 'Tataconsultancy'

    def test_public_domain_not_used_as_company(self):
        body = "Regards\nRajesh"
        r = extract_signature(body, None, 'Rajesh', 'rajesh@gmail.com')
        assert r['company'] is None

    def test_website_from_domain(self):
        body = "Regards"
        r = extract_signature(body, None, 'Test', 'info@mycompany.com')
        assert r['website'] == 'www.mycompany.com'


class TestSignatureZone:
    def test_delimiter_isolation(self):
        body = (
            "Hello, see attached.\n\n"
            "On Monday, we discussed...\n"
            "Please review.\n\n"
            "--\n"
            "John Doe\n"
            "CEO\n"
            "Acme Corp\n"
        )
        r = extract_signature(body, None, 'John', 'john@acme.com')
        assert r['designation'] is not None
        assert 'CEO' in r['designation']

    def test_no_delimiter_uses_tail(self):
        body = (
            "Hi,\n" * 20 +
            "John Doe\n"
            "Director\n"
            "Acme Industries Ltd\n"
        )
        r = extract_signature(body, None, 'John', 'john@acme.com')
        assert r['company'] is not None


class TestCityExtraction:
    def test_known_city(self):
        body = "Contact us in Bangalore 560001"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['city'] == 'Bangalore'
        assert r['pincode'] == '560001'

    def test_unknown_city(self):
        body = "Visit us at 123 Main Street"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['city'] is None


class TestAddressExtraction:
    def test_address_with_keyword(self):
        body = "123 MG Road, Andheri East\nMumbai 400069"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['address'] is not None
        assert 'Road' in r['address'] or 'road' in r['address']

    def test_address_with_pincode(self):
        body = "Visit our office at Plot 45, Industrial Area\nMumbai 400069"
        r = extract_signature(body, None, 'Test', 'test@test.com')
        assert r['address'] is not None
