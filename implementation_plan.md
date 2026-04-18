# Email Validation API Integration

This plan outlines the approach to adding an Email Validation feature. It will allow users to automatically verify email addresses from the uploaded dataset using an external Email Validation API.

## Proposed Changes

### UI & UX Additions
1. **New "Email Validation" Interface**:
   - Add a "Validate Emails" card/button in the existing **Data Quality** view (or a dedicated tab).
   - Display the total number of emails found in the dataset ready for validation.
2. **Settings/API Key Prompt**:
   - If the user hasn't provided an API key for the validation service, prompt them via a sleek modal. We'll securely save this key to their `localStorage` or `config.js`.
3. **Processing State**:
   - Similar to the main dashboard build process, show a dedicated progress bar specifically for the API validation process (since it involves network calls matching the number of emails).
4. **Data Table Updates**:
   - Add a newly generated column: `Email Status` (e.g., Valid, Invalid, Risky).
   - Use badge styling in the table to easily visually distinguish valid from invalid emails.

### Technical Implementation

#### [MODIFY] `index.html`
- Add a "Validate Emails" actionable card in the `view-quality` container.
- Add a generic API Key input modal.
- Add a validation progress view (similar to the existing `view-processing`).

#### [MODIFY] `app.js`
- Create a new `validateEmails()` function.
- Detect which column is mapped as "Email".
- Iterate through the dataset, send GET/POST requests to the validation API.
- Re-render the table and Data Quality charts with the new validation metadata once complete.

---

> [!CAUTION] 
> **User Review Required: Open Questions**
> 
> Before I proceed with execution, I need to know the specific API you intend to use so I can format the HTTP requests and parse the response correctly.
> 
> 1. What is the specific **Valid Email API** service you want to use? (e.g., Hunter.io, ZeroBounce, AbstractAPI, validemail.com, etc.)
> 2. Do you have the API documentation link or an API Key ready? 
> 3. Does the API allow bulk array validation, or should I send requests individually for each row?

## Verification Plan
1. **Mock Data Test**: Start the dev server, upload a small dummy file with intentionally fake/bad emails and some real ones.
2. **API Verification**: Enter the API key, run the validation tool, and observe the Network tab to ensure requests format perfectly.
3. **UI Verification**: Ensure the Data Table accurately updates with "Valid" or "Invalid" badges after the checks finish.
