"""
Heuristic email signature extraction — ported from app.js extractSignatureData().
"""
import re
from html.parser import HTMLParser

# --- Public email domains (skip company fallback) ---
_PUBLIC_DOMAINS = frozenset({
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'rediffmail.com', 'icloud.com', 'protonmail.com', 'live.com',
    'aol.com', 'mail.com', 'zoho.com', 'yandex.com', 'gmx.com',
})

# --- Phone patterns ---
_PHONE_RE = re.compile(r'(?:\+?91[\s\-]?)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{6,14}')

# --- Designation keywords ---
_DESG_RE = re.compile(
    r'\b(ceo|cto|cfo|coo|founder|co-founder|co founder|director|managing director|md|'
    r'manager|general manager|gm|head|vp|vice president|president|engineer|architect|'
    r'developer|consultant|analyst|executive|senior executive|officer|lead|team lead|'
    r'partner|proprietor|agm|dgm|commercial manager|purchase officer|sales manager|'
    r'business development manager|bdm|hr manager|operations manager|'
    r'quality manager|finance manager|accounts manager|project manager|'
    r'plant head|production head|technical head|marketing head|'
    r'senior manager|deputy manager|assistant manager|'
    r'chief|principal|superintendent|supervisor|coordinator|'
    r'designation|position|title)\b',
    re.IGNORECASE,
)

# --- Company suffix keywords ---
_COMP_SUFFIX_RE = re.compile(
    r'\b(ltd|pvt|pvt\.?\s*ltd\.?|inc|corp|llp|llc|industries|solutions|'
    r'technologies|systems|services|enterprises|group|associates|consulting|'
    r'trading|mfg|manufacturing|exports|imports|infra|works|packers|logistics|'
    r'company|co\.?|corporation|holdings|ventures|agency|'
    r'developers|constructors|fabricators|engineers|analysts|'
    r'pharma|textiles|metals|chemicals|electronics|automobiles|motors|'
    r'foundation|institute|academy|college|school|university)\b',
    re.IGNORECASE,
)

# --- Signature delimiter ---
_SIG_DELIM_RE = re.compile(
    r'^(?:--|regards|best regards|thanks|warm regards|sincerely|cheers|'
    r'thanks & regards|thanks and regards|sent from my|with regards|'
    r'kind regards|best wishes|warm wishes|looking forward|'
    r'please note|disclaimer|confidentiality)',
    re.IGNORECASE,
)

# --- Thread/forwarding removal ---
_THREAD_RE = re.compile(
    r'(-{3,}\s*Forwarded message\s*-{3,}|'
    r'-{3,}\s*Original Message\s*-{3,}|'
    r'From:\s*.*?\nSent:\s*|'
    r'On\s+.*?\s+wrote:)[\s\S]*',
    re.IGNORECASE,
)

# --- Address keywords ---
_ADDR_RE = re.compile(
    r'\b(road|rd|street|st|nagar|colony|sector|plot|phase|industrial|estate|'
    r'gidc|complex|tower|building|floor|lane|avenue|boulevard|marg|path|'
    r'cross|junction|market|area|zone|district|state|country)\b',
    re.IGNORECASE,
)

# --- Indian cities (expanded: 100+) ---
_CITIES = (
    'mumbai', 'bombay', 'delhi', 'new delhi', 'bangalore', 'bengaluru',
    'hyderabad', 'ahmedabad', 'ahmadabad', 'chennai', 'madras', 'kolkata',
    'calcutta', 'surat', 'pune', 'poona', 'jaipur', 'vadodara', 'baroda',
    'rajkot', 'noida', 'greater noida', 'gurgaon', 'gurugram', 'thane',
    'ghaziabad', 'faridabad', 'ludhiana', 'chandigarh', 'indore', 'bhopal',
    'patna', 'visakhapatnam', 'vizag', 'nagpur', 'lucknow', 'kanpur',
    'coimbatore', 'madurai', 'thiruvananthapuram', 'trivandrum', 'kochi',
    'ernakulam', 'mysore', 'mysuru', 'hubli', 'dharwad', 'belgaum',
    'belagavi', 'mangalore', 'mangaluru', 'goa', 'panaji', 'udaipur',
    'jodhpur', 'ajmer', 'varanasi', 'prayagraj', 'allahabad',
    'dehradun', 'haridwar', 'rishikesh', 'jammu', 'srinagar', 'amritsar',
    'jalandhar', 'patiala', 'bathinda', 'hisar', 'karnal', 'rohtak',
    'panipat', 'sonipat', 'ambala', 'yamunanagar',
    'raipur', 'bilaspur', 'bhilai', 'ranchi', 'jamshedpur', 'dhanbad',
    'bokaro', 'siliguri', 'darjeeling', 'guwahati', 'dispur', 'shillong',
    'imphal', 'agartala', 'aizawl', 'kohima', 'dimapur', 'gangtok',
    'itanagar', 'bhubaneswar', 'cuttack', 'rourkela', 'berhampur',
    'warangal', 'karimnagar', 'nizamabad', 'khammam', 'nellore',
    'guntur', 'tirupati', 'vijayawada', 'rajahmundry', 'kakinada',
    'anantapur', 'kurnool', 'cuddapah', 'chittoor', 'ongole',
    'hubballi', 'ballari', 'kalaburagi', 'gadag', 'haveri',
    'davangere', 'shimoga', 'shivamogga', 'chitradurga', 'tumakuru',
    'hassan', 'mandya', 'chamarajanagar', 'kodagu', 'kolar',
    'bangarpet', 'hosur', 'krishnagiri', 'dharmapuri', 'salem',
    'erode', 'karur', 'tiruchirappalli', 'trichy', 'thanjavur',
    'tirunelveli', 'thoothukudi', 'tuticorin', 'kanyakumari',
    'nagercoil', 'ramanathapuram', 'sivaganga', 'pudukkottai',
    'dindigul', 'virudhunagar', 'theni', 'cuddalore', 'tiruvannamalai',
    'viluppuram',
    'nashik', 'aurangabad', 'nagpur', 'solapur', 'kolhapur',
    'sangli', 'satara', 'sindhudurg', 'ratnagiri', 'raigad',
    'ahmednagar', 'beed', 'osmanabad', 'latur',
    'parbhani', 'hingoli', 'jalna', 'washim', 'buldhana',
    'akola', 'amravati', 'yeotmal', 'wardha', 'gondia',
    'bhandara', 'chandrapur', 'gadchiroli', 'nandurbar', 'dhule',
    'jalgaon', 'chalisgaon', 'bhusawal',
)

_CITY_RE = re.compile(r'\b(' + '|'.join(_CITIES) + r')\b', re.IGNORECASE)


class _HTMLSigExtractor(HTMLParser):
    """Find signature blocks in HTML email bodies."""

    _SIG_SELECTORS = {
        'gmail_signature', 'signature', 'sig',
    }

    def __init__(self):
        super().__init__()
        self._in_sig = False
        self._depth = 0
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = attr_dict.get('class', '').lower()
        elem_id = attr_dict.get('id', '').lower()
        if any(s in classes for s in self._SIG_SELECTORS) or \
           any(s in elem_id for s in self._SIG_SELECTORS) or \
           tag == 'footer':
            self._in_sig = True
            self._depth = 0
        if self._in_sig:
            self._depth += 1

    def handle_endtag(self, tag):
        if self._in_sig:
            self._depth -= 1
            if self._depth <= 0:
                self._in_sig = False

    def handle_data(self, data):
        if self._in_sig:
            self._text_parts.append(data)

    def get_signature_text(self):
        return '\n'.join(self._text_parts).strip()


def _extract_html_signature(html_body):
    """Extract signature text from HTML using structural cues."""
    if not html_body:
        return None
    try:
        parser = _HTMLSigExtractor()
        parser.feed(html_body)
        text = parser.get_signature_text()
        if 10 < len(text) < 2500:
            return text
    except Exception:
        pass
    return None


def _isolate_signature_zone(text):
    """Strip thread/forwarding content, find signature delimiter, return sig lines."""
    if not text:
        return []
    cleaned = _THREAD_RE.sub('', text)
    lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
    sig_idx = -1
    for i, line in enumerate(lines):
        if _SIG_DELIM_RE.match(line):
            sig_idx = max(0, i - 1)
            break
    if sig_idx != -1:
        return lines[sig_idx:]
    # No delimiter — take last 35 lines
    return lines[max(0, len(lines) - 35):]


def _extract_phones(sig_lines):
    """Extract phone numbers from signature lines."""
    found = []
    for line in sig_lines:
        cleaned = re.sub(r'[\s\(\)\-\.]', '', line)
        for m in _PHONE_RE.finditer(cleaned):
            if m.group(0) not in found:
                found.append(m.group(0))
    return found[0] if found else None, found[1] if len(found) > 1 else None


def _extract_website(sig_lines):
    """Extract website URL from signature lines."""
    web_re = re.compile(r'(?:www\.|https?://)[^\s<>,"\'\)]+')
    for line in sig_lines:
        m = web_re.search(line)
        if m:
            return m.group(0).rstrip('.,;:!?')
    return None


def _extract_designation(sig_lines):
    """Extract job title/designation from signature lines."""
    for line in sig_lines:
        if _DESG_RE.search(line) and len(line) < 90:
            return re.sub(r'^[\|\-•·]\s*', '', line).strip()
    return None


def _extract_company(sig_lines):
    """Extract company name from signature lines (by suffix keyword)."""
    for line in sig_lines:
        if _COMP_SUFFIX_RE.search(line) and len(line) < 100:
            return re.sub(r'^[\|\-•·]\s*', '', line).strip()
    return None


def _extract_pincode(body_text):
    """Extract Indian 6-digit pincode."""
    if not body_text:
        return None
    m = re.search(r'\b([1-9]\d{5})\b', body_text)
    return m.group(1) if m else None


def _extract_city(body_text):
    """Extract city name from body text."""
    if not body_text:
        return None
    m = _CITY_RE.search(body_text)
    if m:
        city = m.group(0)
        return city[0].upper() + city[1:].lower()
    return None


def _extract_address(sig_lines, pincode):
    """Extract address line from signature lines."""
    for line in sig_lines:
        if _ADDR_RE.search(line) or (pincode and pincode in line):
            if 10 < len(line) < 160:
                return re.sub(r'^[\|\-•·]\s*', '', line).strip()
    return None


def _company_from_domain(from_email):
    """Derive company name and website from email domain (non-public only)."""
    if not from_email or '@' not in from_email:
        return None, None
    domain = from_email.split('@')[1].lower()
    if domain in _PUBLIC_DOMAINS:
        return None, None
    website = 'www.' + domain
    comp_name = domain.split('.')[0]
    company = comp_name[0].upper() + comp_name[1:]
    return company, website


def _calculate_confidence(result):
    """Confidence score: name(20) + email(20) + phone(25) + company(20) + designation(15) = 100."""
    score = 0
    if result.get('name'):
        score += 20
    if result.get('email'):
        score += 20
    if result.get('phone_primary'):
        score += 25
    if result.get('company'):
        score += 20
    if result.get('designation'):
        score += 15
    return score


def extract_signature(body_text, html_body, from_name, from_email):
    """
    Main entry point — extract contact signature from email body.

    Args:
        body_text: Plain text email body
        html_body: HTML email body (optional, for structural signature detection)
        from_name: Sender display name
        from_email: Sender email address

    Returns:
        dict with keys: name, email, company, designation, phone_primary,
        phone_secondary, website, address, city, pincode, confidence
    """
    result = {
        'name': from_name or None,
        'company': None,
        'designation': None,
        'phone_primary': None,
        'phone_secondary': None,
        'email': from_email or None,
        'website': None,
        'address': None,
        'city': None,
        'pincode': None,
        'confidence': 0,
    }

    # 1. Try HTML structural parsing
    if html_body:
        sig_text = _extract_html_signature(html_body)
        if sig_text:
            body_text = sig_text + '\n' + (body_text or '')

    if not body_text and not from_email:
        return result
    body_text = body_text or ''

    # 2. Isolate signature zone
    sig_lines = _isolate_signature_zone(body_text)

    # 3. Extract phones
    result['phone_primary'], result['phone_secondary'] = _extract_phones(sig_lines)

    # 4. Extract website
    result['website'] = _extract_website(sig_lines)

    # 5. Extract designation
    result['designation'] = _extract_designation(sig_lines)

    # 6. Extract company (from signature lines)
    result['company'] = _extract_company(sig_lines)

    # 7. Domain fallback for company + website
    dom_company, dom_website = _company_from_domain(from_email)
    if dom_website and not result['website']:
        result['website'] = dom_website
    if dom_company and not result['company']:
        result['company'] = dom_company

    # 8. Pincode, city, address
    result['pincode'] = _extract_pincode(body_text)
    result['city'] = _extract_city(body_text)
    result['address'] = _extract_address(sig_lines, result['pincode'])

    # 9. Confidence
    result['confidence'] = _calculate_confidence(result)

    return result
