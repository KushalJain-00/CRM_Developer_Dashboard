import xlrd
import pdfplumber
import openpyxl
import io
import re
from typing import Any


def parse_xls(content: bytes) -> dict:
    """
    Parse ALL valid sheets in an XLS workbook and merge
    them into a single unified dataset.
    """
    wb = xlrd.open_workbook(file_contents=content)
    all_rows = []
    all_headers = []
    sheet_names_used = []

    for name in wb.sheet_names():
        # Skip lookup / index sheets
        lname = name.lower()
        if re.search(r"mob no|email id|phone list|mobile list|index|lookup", lname):
            continue

        sheet = wb.sheet_by_name(name)
        if sheet.nrows < 2 or sheet.ncols <= 2:
            continue

        headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
        headers = [h for h in headers if h]  # drop blank headers

        # Track all unique headers across sheets
        for h in headers:
            if h not in all_headers:
                all_headers.append(h)

        for r in range(1, sheet.nrows):
            row = {}
            for c, h in enumerate(headers):
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
    rows = []
    headers = None

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if not table:
                        continue
                    if headers is None and len(table) > 1:
                        raw_headers = [str(c).strip() if c else f"Col_{i}" for i, c in enumerate(table[0])]
                        headers = _dedupe_headers(raw_headers)
                        data_rows = table[1:]
                    else:
                        data_rows = table[1:] if headers and table[0] == table[0] else table
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
                text = page.extract_text()
                if text:
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
