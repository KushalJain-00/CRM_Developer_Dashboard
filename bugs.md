# CRM Bug Registry

## Data Segregation & Field Mapping (Auto-Detect)
- **Bug**: The system currently creates different fields dynamically based on the sheet name.
- **Expected Behavior**: We need auto-detection and data segregation that maps to a standard set of fixed fields, regardless of the sheet name.
- **Required Standard Fields**:
  1. Name of the Company
  2. Location of the Company
  3. Website of the Company
  4. Name of the Person - 1
  5. Name of the Person - 2
  6. Mobile Number of the Person - 1
  7. Mobile Number of the Person - 2
  8. Email ID of the Person - 1
  9. Email ID of the Person - 2
  10. Products / Misc

## Phone Number Extraction
- **Bug**: The system is catching all types of contact numbers, including landlines and fax numbers.
- **Expected Behavior**: We only need to catch **Mobile numbers**. Telephonic landline and fax numbers are of no use and should be ignored/filtered out during extraction.

# CRM Application - Potential Bugs & Logic Flaws

After reviewing the codebase (`frontend/app.js` and `api/contacts.py`), here are several potential bugs and logic errors that could impact data integrity and user experience.

## 1. Frontend: Modal Validation Bypass (`frontend/app.js`)
**Location:** `saveEdit()` function (around line 1481)
**Issue:** 
The edit modal validation uses `return` inside a `.forEach()` loop over the input fields. 
```javascript
inputs.forEach(inp => {
  // ...
  if (type === 'email' && val && !isValidEmail(val)) {
    inp.style.border = '2px solid var(--rose)';
    showNotification('Invalid email: ' + val, 'error');
    return; // 🐛 BUG: Only exits this iteration!
  }
  // ...
});
S.filtered[_editIdx] = row;
closeEditModal();
renderTable();
```
**Impact:** Returning inside a `forEach` loop acts like a `continue` statement. It skips the current field but does **not** stop the function execution. As a result, the modal will still close and save the invalid data to the row state, ignoring the validation error entirely. 
**Fix:** Use a standard `for...of` loop so you can `return` out of the entire `saveEdit()` function, or use a boolean flag (e.g., `let hasError = false;`) and abort the save if it evaluates to true.

---

## 2. Backend: Ignored Company Updates (`api/contacts.py`)
**Location:** `update_contact` route (around line 354)
**Issue:** 
When updating a contact via the `PUT /contacts/{contact_id}` route, the code checks if `contact.company_id` exists before updating company details.
```python
if contact.company_id:
    company = db.query(Company).filter(Company.id == contact.company_id).first()
    # Updates company name, address, etc.
```
**Impact:** If a contact was originally created *without* a company, and the user edits the contact later to add a `company_name`, the backend completely ignores it. It does not create a new `Company` row and does not link it, leading to silently discarded user input.
**Fix:** Add an `else` branch to create a new `Company` (or find an existing one using `_find_or_create_company`) and assign its ID to `contact.company_id`.

---

## 3. Backend: Large Payload Failure in Bulk Deletes (`api/contacts.py`)
**Location:** `delete_multiple` route (line 387)
**Issue:** 
The bulk delete route passes a list of IDs directly to a SQL `IN` clause:
```python
deleted = db.query(Contact).filter(Contact.id.in_(ids)).delete(...)
```
**Impact:** If the user attempts to delete a massive number of contacts at once (e.g., 50,000+), this query may fail. Databases have hard limits on the number of bind parameters allowed in a single query (e.g., PostgreSQL limit is often 32,767 or 65,535 parameters).
**Fix:** Check if the list is empty (to avoid empty IN clause syntax errors on some SQL drivers) and chunk the IDs array into smaller batches (e.g., 10,000 at a time) before executing the delete.

---

## 4. Backend/Logic: Discarded Raw Data on Import (`api/contacts.py`)
**Location:** `batch_import` route (line 220)
**Issue:**
During batch import, if a row is detected as a duplicate (email or phone already exists), it executes `continue`:
```python
if has_email and item.email_primary in existing_emails:
    skipped += 1
    continue
```
**Impact:** Because the loop `continue`s immediately, it completely skips the raw data archiving step (`db.add(Record(...))`) at the bottom of the loop. If a user ever wants to inspect the raw JSON payload of the skipped records for audit or recovery purposes, they will be missing from the `session.records` relationship.
**Fix:** If you intend to keep a record of all uploaded rows regardless of whether they were imported into the CRM or skipped as duplicates, move the `db.add(Record(...))` block to the top of the loop before any `continue` statements.

---

## Room for Improvements

While reviewing the code, several structural and architectural improvements were identified that could elevate the performance, security, and maintainability of the CRM application:

### 1. Security: Cross-Site Scripting (XSS) Vulnerabilities (`frontend/app.js`)
Currently, extensive amounts of raw dataset values are injected directly into the DOM via `.innerHTML` (e.g., rendering table rows `<td>${v}</td>`, chart tooltips, and duplicate cards). If a malicious user imports a CSV with HTML or `<script>` tags embedded in fields like "Company Name", it could result in an XSS attack executing in the browser of anyone viewing the dashboard.
**Improvement:** Implement an HTML sanitization function or use `textContent` / `document.createElement()` instead of template literal injections for user-provided data.

### 2. Performance: UI Thread Blocking (`frontend/app.js`)
Data cleaning, parsing, and the `findDuplicates` operations run synchronously on the main UI thread. 
**Improvement:** Processing thousands of records simultaneously will cause the browser UI to freeze or stutter ("Application Not Responding"). Migrating `processData()`, `buildMapping()`, and deduplication loops to a **Web Worker** would keep the dashboard animations and UI perfectly smooth regardless of the dataset size.

### 3. Architecture: Monolithic Frontend Codebase
The entire frontend application logic, including DOM manipulation, API fetching, Supabase auth, complex data cleaning heuristics, charting, and PDF export logic, is stuffed into a single `app.js` file (~2,800+ lines). 
**Improvement:** Refactor `app.js` into smaller ES Modules (e.g., `api.js`, `ui-components.js`, `data-processing.js`, `charts.js`). This would drastically improve maintainability, readability, and modularity.

### 4. Backend Performance: OFFSET Pagination (`api/contacts.py`)
The `GET /contacts` listing API uses traditional `OFFSET / LIMIT` pagination. 
**Improvement:** As the CRM database grows to hundreds of thousands or millions of records, deep `OFFSET` queries become very slow because the database must scan and discard all preceding rows. Transitioning to **Cursor-based Pagination** (Keyset pagination, e.g., `WHERE id > last_seen_id LIMIT 50`) will guarantee consistent query speeds at any scale.

### 5. Data Quality: Advanced Deduplication Algorithms
The current deduplication logic for company names relies on basic string truncation: `name.toLowerCase().replace(/[^a-z0-9]/g,'').slice(0,20)`. 
**Improvement:** This naive approach can yield both false positives (similar prefixes) and false negatives (typos). Utilizing a fuzzy matching library like `Fuse.js` on the frontend, or implementing Levenshtein distance matching on the PostgreSQL backend, would provide a significantly more robust and intelligent deduplication process.

---

# PDF Parsing Bugs (Discovered During Audit) — ✅ FIXED

## 5. PDF Import: Broken Duplicate Header Detection (`services/parser.py`)
**Location:** `parse_pdf()` function, line 96
**Issue:** The condition `table[0] == table[0]` always evaluates to `True` (comparing a list to itself). This was meant to check if a subsequent table's first row repeats the header row, but instead it always skips row 0 as a header — losing real data rows from subsequent tables.
**Status:** ✅ Fixed — Now properly compares cleaned first-row values against stored headers.

## 6. PDF Import: Weak Text Fallback for Non-Tabular PDFs (`services/parser.py`)
**Location:** `parse_pdf()` text extraction fallback, line 108-119
**Issue:** When a PDF has no tables, the fallback simply splits lines by whitespace/tabs. It doesn't use regex patterns to extract phones, emails, or URLs — missing valuable contact data from paragraph-format PDFs.
**Status:** ✅ Fixed — Added regex-based extraction for mobile numbers (`[6-9]\d{9}`), emails, and URLs before falling back to generic line splitting.

## 7. PDF Import: No Page Limit / Memory Risk (`services/parser.py`)
**Location:** `parse_pdf()` page loop
**Issue:** No upper bound on number of pages processed. `pdfplumber` can use 5-10x memory of the original file size. A 30MB PDF with 500+ pages could exhaust server memory.
**Status:** ✅ Fixed — Added `MAX_PAGES = 100` limit.

## 8. PDF Export: Filename Injection in Content-Disposition Header (`api/export_pdf.py`)
**Location:** `export_pdf()` route, line 41
**Issue:** `body.fileName` was injected directly into the `Content-Disposition` HTTP header without sanitization. A filename containing `"` or newline characters could break the header or enable HTTP header injection.
**Status:** ✅ Fixed — Filename is now sanitized with `re.sub(r'[^\w\s\-\.]', '', ...)` before injection.
