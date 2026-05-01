import xlrd
import pdfplumber
import openpyxl
import io
import re
import time
from typing import Any


def parse_xls(content: bytes) -> dict:
    """
    Parse ALL valid sheets in an XLS workbook and merge
    them into a single unified dataset.
    """
    start_time = time.time()
    wb = xlrd.open_workbook(file_contents=content)
    all_rows = []
    all_headers = []
    sheet_names_used = []

    for name in wb.sheet_names():
        if time.time() - start_time > 15:
            raise TimeoutError("XLS processing exceeded 15 seconds limit")
            
        # Skip lookup / index sheets
        lname = name.lower()
        if re.search(r"mob no|email id|phone list|mobile list|index|lookup", lname):
            continue

        sheet = wb.sheet_by_name(name)
        if sheet.nrows < 2 or sheet.ncols <= 2:
            continue

        # Map column index to header name, skipping blank headers
        header_map = {}
        for c in range(sheet.ncols):
            h = str(sheet.cell_value(0, c)).strip()
            if h:
                header_map[c] = h
                if h not in all_headers:
                    all_headers.append(h)

        for r in range(1, sheet.nrows):
            if time.time() - start_time > 15:
                raise TimeoutError("XLS processing exceeded 15 seconds limit")
                
            row = {}
            for c, h in header_map.items():
                if c >= sheet.ncols:
                    break
                cell = sheet.cell(r, c)
                val = cell.value
                if cell.ctype == xlrd.XL_CELL_NUMBER:
                    val = int(val) if val == int(val) else val
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    from xlrd import xldate_as_tuple
                    import datetime
                    try:
                        t = xldate_as_tuple(val, wb.datemode)
                        val = str(datetime.date(*t[:3]))
                    except Exception:
                        val = str(val)
                else:
                    val = str(val).strip() if val else ""
                row[h] = val if val != "" else None
            if any(v for v in row.values() if v is not None):
                all_rows.append(row)
        sheet_names_used.append(name)

    if not all_rows:
        raise ValueError("No data found in any sheet")

    combined_name = " + ".join(sheet_names_used) if len(sheet_names_used) > 1 else sheet_names_used[0]
    return {"sheet": combined_name, "headers": all_headers, "rows": all_rows}


def parse_pdf(content: bytes) -> dict:
    start_time = time.time()
    rows = []
    headers = None
    MAX_PAGES = 200  # Memory safety: limit pages processed
    all_text_pages = []  # Collect text from all pages for fallback

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if time.time() - start_time > 30:
                raise TimeoutError("PDF processing exceeded 30 seconds limit")
            if page_num >= MAX_PAGES:
                break

            tables = page.extract_tables()
            table_found = False
            if tables:
                for table in tables:
                    if not table:
                        continue
                    # Filter out rows that are completely empty
                    table = [r for r in table if r and any(c for c in r if c)]
                    if not table:
                        continue
                    table_found = True
                    if headers is None and len(table) > 1:
                        # First table: row 0 = headers
                        raw_headers = [str(c).strip() if c else f"Col_{i}" for i, c in enumerate(table[0])]
                        headers = _dedupe_headers(raw_headers)
                        data_rows = table[1:]
                    else:
                        # Subsequent tables: check if row 0 repeats the header
                        if headers and len(table) > 0:
                            first_row_cleaned = [str(c).strip() if c else '' for c in table[0]]
                            header_cleaned = [h.strip() for h in headers]
                            if first_row_cleaned == header_cleaned:
                                data_rows = table[1:]  # Skip repeated header row
                            else:
                                data_rows = table
                        else:
                            data_rows = table
                    for raw_row in data_rows:
                        if not any(c for c in raw_row if c):
                            continue
                        if headers:
                            row = {headers[i]: str(raw_row[i]).strip() if i < len(raw_row) and raw_row[i] else None
                                   for i in range(len(headers))}
                        else:
                            row = {f"Col_{i}": str(v).strip() if v else None for i, v in enumerate(raw_row)}
                        if any(v for v in row.values() if v):
                            rows.append(row)

            # Collect page text for fallback
            text = page.extract_text()
            if text and not table_found:
                all_text_pages.append(text)

    # If tables produced enough rows, return them
    if rows and len(rows) >= 2:
        if headers is None:
            headers = list(rows[0].keys()) if rows else []
        return {"sheet": "PDF Import", "headers": headers, "rows": rows}

    # ── Fallback: Extract structured data from raw text ─────────────
    full_text = '\n'.join(all_text_pages)
    if not full_text.strip():
        if rows:
            headers = headers or list(rows[0].keys())
            return {"sheet": "PDF Import", "headers": headers, "rows": rows}
        raise ValueError("No tabular data or text could be extracted from PDF")

    rows = _extract_contacts_from_text(full_text)

    if not rows:
        raise ValueError("No structured contact data could be extracted from PDF")

    headers = list(rows[0].keys()) if rows else []
    return {"sheet": "PDF Import", "headers": headers, "rows": rows}


def _extract_contacts_from_text(text: str) -> list:
    """
    Extract structured contact records from free-form PDF text.
    Tries multiple strategies: regex extraction, block parsing, line splitting.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return []

    # Regex patterns
    phone_re = re.compile(r'(?:\+91[\s\-]?)?[6-9]\d{9}')
    intl_phone_re = re.compile(r'\+\d{1,3}[\s\-]?\d{5,14}')
    email_re = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
    url_re = re.compile(r'(?:https?://|www\.)[^\s,;]+', re.I)
    pincode_re = re.compile(r'\b[1-9]\d{5}\b')

    # Strategy 1: Group lines into blocks separated by blank-ish gaps or numbering
    blocks = []
    current_block = []
    prev_line = ""
    for line in lines:
        # Detect block boundaries: numbered entries, blank lines, or lines starting with SR/No
        is_boundary = (
            re.match(r'^\d{1,4}[\.\)\s]', line) and len(current_block) > 2
        )
        if is_boundary and current_block:
            blocks.append('\n'.join(current_block))
            current_block = []
        current_block.append(line)
        prev_line = line

    if current_block:
        blocks.append('\n'.join(current_block))

    # If we got reasonable blocks, extract from each
    if len(blocks) >= 3:
        rows = []
        for block in blocks:
            row = _extract_fields_from_block(block, phone_re, intl_phone_re, email_re, url_re, pincode_re)
            if row and any(v for v in row.values() if v):
                rows.append(row)
        if rows:
            return rows

    # Strategy 2: Line-by-line extraction — collect all phones/emails
    # and build records from proximity
    all_phones = phone_re.findall(text) + intl_phone_re.findall(text)
    all_emails = email_re.findall(text)

    if all_phones or all_emails:
        rows = []
        # Deduplicate
        seen_phones = set()
        seen_emails = set()
        for p in all_phones:
            cleaned = re.sub(r'[\s\-]', '', p)
            if cleaned not in seen_phones:
                seen_phones.add(cleaned)
        for e in all_emails:
            if e.lower() not in seen_emails:
                seen_emails.add(e.lower())

        unique_phones = list(seen_phones)
        unique_emails = list(seen_emails)

        max_items = max(len(unique_phones), len(unique_emails), 1)
        for j in range(max_items):
            row = {}
            if j < len(unique_phones):
                row['Phone'] = unique_phones[j]
            if j < len(unique_emails):
                row['Email'] = unique_emails[j]
            if any(v for v in row.values() if v):
                rows.append(row)
        if rows:
            return rows

    # Strategy 3: Split by delimiters
    rows = []
    for line in lines:
        parts = re.split(r'\s{2,}|\t', line)
        if len(parts) >= 2:
            row = {f"Col_{i}": p.strip() for i, p in enumerate(parts) if p.strip()}
            if len(row) >= 2:
                rows.append(row)

    return rows


def _extract_fields_from_block(block: str, phone_re, intl_phone_re, email_re, url_re, pincode_re) -> dict:
    """Extract contact fields from a text block."""
    row = {}
    phones = phone_re.findall(block)
    intl_phones = intl_phone_re.findall(block)
    all_phones = phones + intl_phones
    emails = email_re.findall(block)
    urls = url_re.findall(block)
    pincodes = pincode_re.findall(block)

    if all_phones:
        row['Phone'] = all_phones[0]
        if len(all_phones) > 1:
            row['Phone 2'] = all_phones[1]
    if emails:
        row['Email'] = emails[0]
    if urls:
        row['Website'] = urls[0]
    if pincodes:
        row['Pincode'] = pincodes[0]

    # Try to extract company/person name from first line
    lines = block.strip().split('\n')
    if lines:
        first_line = re.sub(r'^\d{1,4}[\.\)\s]+', '', lines[0]).strip()
        # If first line doesn't look like a phone/email, treat as name
        if first_line and not phone_re.search(first_line) and not email_re.search(first_line):
            # Check if it looks like a company
            comp_re = re.compile(r'\b(ltd|pvt|inc|corp|llp|llc|industries|solutions|technologies|systems|services|enterprises|group|associates)\b', re.I)
            if comp_re.search(first_line):
                row['Company'] = first_line[:120]
            else:
                row['Name'] = first_line[:80]

    # Look for address-like content
    addr_parts = []
    for line in lines[1:]:
        line_clean = line.strip()
        if not line_clean:
            continue
        # Skip lines that are just phones/emails
        if phone_re.fullmatch(line_clean) or email_re.fullmatch(line_clean):
            continue
        if url_re.fullmatch(line_clean):
            continue
        # If line has address keywords, add it
        if re.search(r'\b(road|street|nagar|plot|block|estate|phase|sector|area|dist|taluka|gujarat|maharashtra|delhi|mumbai|chennai|kolkata|bangalore|hyderabad|pune|ahmedabad|surat|vadodara|rajkot|gidc|industrial)\b', line_clean, re.I):
            addr_parts.append(line_clean)

    if addr_parts:
        row['Address'] = ', '.join(addr_parts)[:200]

    return row


def _dedupe_headers(headers: list) -> list:
    seen = {}
    result = []
    for h in headers:
        h = h or "Unnamed"
        if h in seen:
            seen[h] += 1
            result.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            result.append(h)
    return result
