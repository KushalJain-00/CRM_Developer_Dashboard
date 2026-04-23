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
    MAX_PAGES = 100  # Memory safety: limit pages processed

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if time.time() - start_time > 15:
                raise TimeoutError("PDF processing exceeded 15 seconds limit")
            if page_num >= MAX_PAGES:
                break

            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if not table:
                        continue
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
            else:
                # Fallback: extract structured data from plain text using regex
                text = page.extract_text()
                if text:
                    # Try to extract phone numbers and emails from text
                    phones = re.findall(r'(?:\+91[\s\-]?)?[6-9]\d{9}', text)
                    emails = re.findall(r'[\w.+%-]+@[\w.-]+\.[a-z]{2,}', text, re.I)
                    urls = re.findall(r'https?://[^\s]+|www\.[^\s]+', text)

                    if phones or emails:
                        # Build rows from extracted contact data
                        if headers is None:
                            h_list = []
                            if phones: h_list.append('Phone')
                            if emails: h_list.append('Email')
                            if urls: h_list.append('Website')
                            headers = _dedupe_headers(h_list if h_list else ['Data'])

                        max_items = max(len(phones), len(emails), 1)
                        for j in range(max_items):
                            row = {}
                            if 'Phone' in headers:
                                row['Phone'] = phones[j] if j < len(phones) else None
                            if 'Email' in headers:
                                row['Email'] = emails[j] if j < len(emails) else None
                            if 'Website' in headers:
                                row['Website'] = urls[j] if j < len(urls) else None
                            if any(v for v in row.values() if v):
                                rows.append(row)
                    else:
                        # Generic line-based fallback
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        for line in lines:
                            parts = re.split(r"\s{2,}|\t|,", line)
                            if len(parts) >= 2:
                                if headers is None:
                                    headers = _dedupe_headers([f"Col_{i}" for i in range(len(parts))])
                                row = {headers[i] if i < len(headers) else f"Col_{i}": p.strip()
                                       for i, p in enumerate(parts)}
                                if any(v for v in row.values() if v):
                                    rows.append(row)

    if not rows:
        raise ValueError("No tabular data could be extracted from PDF")

    if headers is None:
        headers = list(rows[0].keys()) if rows else []

    return {"sheet": "PDF Import", "headers": headers, "rows": rows}


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
