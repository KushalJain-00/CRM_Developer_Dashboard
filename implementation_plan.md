# Implementation Plan - CRM Database Sync & EML Extraction Fixes (Revised)

This plan outlines the root causes of the bugs in the CRM EML extraction, mapping, saving to CRM database, and history rendering, along with the proposed fixes. It incorporates new features for robust EML extraction using full email context, API retries, fallback models, request delays, failure notifications, and attachment file tracking, and ensures that saving and history functionalities work correctly for both standard CRM imports and EML data.

---

## Root Cause Analysis

1. **EML & CRM Contacts Save Skipped (Null Payload)**:
   - When a user pushes EML contacts (`emlSendToCRM()` and `pushBulkToCRM()`), they bypass `normalizeToStandardFields()` and directly open the `'table'` view. As a result, the frontend data table contains columns named `Name`, `Email`, `Company`, `Phone`, `Phone 2`, etc.
   - When saving to the CRM via `saveToCRM()`, the frontend maps standard fields like `row['Person Name 1']`, `row['Email 1']`, etc., to the backend payload. Since the pushed EML rows do not have these standard names, all mapped properties evaluate to `null`.
   - On the backend, contacts without an email or valid mobile are skipped. Thus, 100% of pushed EML records are silently discarded by the backend.
   - For standard Excel, CSV, or PDF imports, if headers are not properly standardized or are left unmapped, contacts are also skipped, preventing them from showing up in the CRM database.
   
2. **Missing Database Field Mapping**:
   - The database schemas for `companies` and `contacts` support separate columns for `address`, `pincode`, `position` (designation), and `whatsapp`. However, `normalizeToStandardFields()` only maps columns to a generic `Location` field and discards separate fields, causing them to be saved as `null`.

3. **Signature Intelligence Extraction Array Incompatibility**:
   - The backend `/api/parse-signature` endpoint returns a JSON array of parsed signature objects (e.g. `[{"name": "...", "email": "..."}]`).
   - The frontend treats `EML.sigData` as a single object (e.g., `sd.name`), resulting in `undefined` values for all fields in the Signature Intelligence panel.
   - The frontend attempts to look up contact signature data using the email as a key (e.g., `sd[c.email]`). Since `sd` is a numeric-indexed array, this lookup fails and returns `undefined`.

4. **Upload History Not Displayed (Orphaned Sessions)**:
   - When users open the app, `syncAuthSession()` initializes the local session from Supabase, but it does not call the `/api/auth/upsert` endpoint. If the user doesn't go through the login page first, their user record does not exist in the backend database.
   - When saving a session, the backend checks for the user's record. Since the user doesn't exist, the session is saved with `user_id = None`.
   - Later, when history retrieves sessions matching the user, it results in inconsistent state mapping.

5. **CRM Edits, Deletes, and Call Logs Not Saving (Mocked UI)**:
   - The frontend includes buttons to Edit contacts, Delete contacts, and Add Call Logs (CRM Phase 2). However, these functions (`saveEdit`, `deleteRow`, `addCallLogFromPanel`) currently only mutate local JavaScript state (`S.filtered` array) or append DOM elements without making any `fetch()` requests to the backend API (`PUT /api/contacts/{id}`, `POST /api/calls`, etc.).
   - Furthermore, the frontend operates on parsed data which doesn't include the backend `contact.id`. Because of this, it cannot construct the appropriate URLs for the backend API.

---

## Proposed Changes

### Database Layer

#### [MODIFY] [db/models.py](file:///d:/PROJECTS/CRM_Developer/db/models.py)
- Add a new column `files = Column(Text)` to the `Contact` model to store comma-separated attachment filenames.

#### [MODIFY] [db/database.py](file:///d:/PROJECTS/CRM_Developer/db/database.py)
- Update `init_db()` to check if the `files` column exists in the `contacts` table, and run an `ALTER TABLE contacts ADD COLUMN files TEXT;` dynamically inside a `try/except` block to support existing databases.

---

### Backend (FastAPI Services & Routes)

#### [MODIFY] [api/contacts.py](file:///d:/PROJECTS/CRM_Developer/api/contacts.py)
- Update the Pydantic schemas `ContactIn` and `ContactUpdate` to include `files: Optional[str] = None`.
- Update `batch_import()` and `update_contact()` to save/update the `files` column.
- Update `_contact_to_dict` to include `files`.
- Update `batch_import()` to track and return the database `contact.id` for each item inside a `contact_ids` array, so the frontend can associate rows with their database records.

#### [MODIFY] [api/history.py](file:///d:/PROJECTS/CRM_Developer/api/history.py)
- Update `get_session_endpoint()` to query existing CRM contacts by email/phone (similar to `export_session_with_calls`) and append the `_contact_id` property to the returned records, so that loaded history sessions can be edited in the frontend.

#### [MODIFY] [api/parse_signature.py](file:///d:/PROJECTS/CRM_Developer/api/parse_signature.py)
- Update the system prompt to instruct the AI to extract contact information from the full email text, not just signatures.
- Remove `extract_signature_block()` so that the full parsed email body and headers are sent for extraction.
- To **save tokens**: Ensure only clean plain-text bodies are processed, removing large base64 attachments, inline images, and HTML/CSS boilerplate.
- Implement a retry handler on the API:
  - If the primary API call fails, retry up to **5 times** using exponential backoff (e.g., 1s, 2s, 4s, 8s, 16s).
  - If all 5 retries fail, fall back to the next model/provider in a configured fallback chain:
    - Primary: user configured (e.g. `groq/llama-3.3-70b-versatile`).
    - Fallback 1: `openrouter/meta-llama/llama-3.3-70b-instruct` (or Gemini Flash).
    - Fallback 2: `openai/gpt-4o-mini`.
  - Apply standard API keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`) from environment variables when fallbacks are used.

---

### Frontend (User Interface & Logic)

#### [MODIFY] [index.html](file:///d:/PROJECTS/CRM_Developer/frontend/index.html)
- Remove the duplicate container with `id="emlSigData"` (lines 316 and 319 both share the same ID).
- Keep the clean single container `<div id="emlSigData" style="display:none"></div>`.

#### [MODIFY] [app.js](file:///d:/PROJECTS/CRM_Developer/frontend/app.js)
- Update `syncAuthSession()` to call the `/api/auth/upsert` API route, ensuring the user record is registered in the backend database.
- Add `files` to `FT` (Field Types): `files: {label:'Attachment Files', icon:'📎', color:'#94A3B8'}`.
- Expand `STANDARD` fields in `normalizeToStandardFields()` to include:
  - `Address` (mapped from type `'address'`)
  - `Pincode` (mapped from type `'pincode'`)
  - `Designation` (mapped from type `'keyword'`)
  - `WhatsApp` (mapped from type `'whatsapp'`)
  - `Files` (mapped from type `'files'`)
- Update `saveToCRM()` to retrieve and map:
  - `address`: `row['Address'] || null`
  - `pincode`: `row['Pincode'] || null`
  - `position`: `row['Designation'] || null`
  - `whatsapp`: `row['WhatsApp'] || null`
  - `files`: `row['Files'] || null`
- Update `saveToCRM()` to process the returned `contact_ids` array and assign `_contact_id` to each row in `S.clean` so the frontend can interact with the backend APIs.
- Wire up `saveEdit()` to make a `PUT /api/contacts/{id}` request when a row has an associated `_contact_id`.
- Wire up `deleteRow()` to make a `DELETE /api/contacts/{id}` request when deleting a row with an associated `_contact_id`.
- Wire up `addCallLogFromPanel()` to make a `POST /api/calls` request using the `_contact_id`.
- Update `renderSigPanel()` to support both single signature objects and arrays of signature objects. If multiple signatures are found, render them as separate blocks.
- Update `emlSendToCRM()` and `pushBulkToCRM()` to:
  - Populate the `Files` column with the comma-separated names of attachments.
  - Call `normalizeToStandardFields()` to map the extracted EML columns to the standard CRM columns (`Person Name 1`, `Mobile 1`, etc.) so that they are successfully saved, pushed, and stored in the database.
- For bulk EML parsing, implement rate-limiting delays (e.g., 500ms delay between files).
- Keep track of files that fail to parse or extract, and show a final summary notification listing the exact files that failed and the error message.

---

## Verification Plan

### Automated/Manual Verification
1. **Startup**: Run the FastAPI backend and verify the SQLite schema update adds the `files` column.
2. **User Creation**: Log in and verify `/api/auth/upsert` successfully creates or updates the user.
3. **EML Parsing & Retries**: Test EML extraction. If the primary model fails or is rate-limited, verify it retries 5 times and then falls back to other providers.
4. **CRM Push**: Push contacts to the CRM. Verify columns like `Person Name 1`, `Mobile 1`, `Address`, `Pincode`, `Designation`, and `Files` (listing attachment names) are mapped correctly in the standard CRM data table.
5. **Database Saving**: Click "Save to CRM", check the database to confirm `files`, `address`, `pincode`, and `position` are stored correctly.
6. **Upload History**: Reload the session from the History tab and check if the contacts display all data accurately.
