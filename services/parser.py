import xlrd
import pdfplumber
import openpyxl
import io
import re
from typing import Any


def parse_xls(content: bytes) -> dict:
    wb = xlrd.open_workbook(file_contents=content)
    best_sheet = _pick_best_xls_sheet(wb)
    sheet = wb.sheet_by_name(best_sheet)
    if sheet.nrows < 2:
        raise ValueError("Sheet appears empty")
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    rows = []
    for r in range(1, sheet.nrows):
        row = {}
        for c, h in enumerate(headers):
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
            rows.append(row)
    return {"sheet": best_sheet, "headers": headers, "rows": rows}


def _pick_best_xls_sheet(wb: xlrd.Book) -> str:
    best, best_score = wb.sheet_names()[0], -1
    for name in wb.sheet_names():
        sheet = wb.sheet_by_name(name)
        cols = sheet.ncols
        rows = sheet.nrows
        if cols <= 2:
            continue
        lname = name.lower()
        if re.search(r"mob no|email id|phone list|mobile list|index|lookup", lname):
            continue
        score = rows * cols
        if score > best_score:
            best_score = score
            best = name
    return best


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
