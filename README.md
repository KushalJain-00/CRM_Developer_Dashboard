# CRM Intelligence

## What it is
CRM Intelligence is a smart contact management platform designed for sales and outreach teams. It automatically reads your email files (`.eml`), extracts the sender's details and signature using AI, and converts them into organized CRM contacts. It cleans the data, catches exact duplicates, and pushes the final contacts into your database.

## Live App
**URL:** [https://crmdevloper.vercel.app](https://crmdevloper.vercel.app)

**First Steps:**
1. Open the URL above.
2. Sign up or log in using your email and password.
3. Once logged in, click **EML Extraction** in the sidebar to start processing emails.

## How to use it, step by step
1. **Upload Files:** Drag and drop your `.eml` files into the upload zone, or click to select them from your computer. You can upload multiple files at once (up to 10MB each).
2. **AI Extraction:** The system reads the email and uses AI to read the signature block and email body.
3. **Extracted Fields:** The AI finds and fills in: Name, Email, Primary Phone, Secondary Phone, Company, Designation, Address, City, Pincode, and Website.
4. **Deduplication:** Before saving, the system checks if the email or phone number already exists in your database. If it does, it marks the new contact as a "DUPLICATE".
5. **Review and Edit:** After processing, you'll see a table of results. Click "View all contacts" to see the full list. You can select contacts using the checkboxes and push them to your main CRM.
6. **Failures:** If a file fails to process (e.g., file too large, AI timeout), it will be marked as "ERROR" in the results table, and the system will skip it.

## LLM Setup (AI Providers)
To extract signatures, the CRM uses AI models. You must provide your own API key to use them. The system uses a "failover chain" — meaning you can set up multiple AI providers. If the first one fails or is too busy, it automatically tries the second one.

**How to add an AI provider:**
1. Open the AI Settings (the gear icon) in the top menu.
2. Select a **Provider** (e.g., Groq, OpenRouter, Gemini).
3. Select a **Model**.
4. Paste your **API Key**.
5. Click **Save**.

**Recommended Free Setup:**
* **Provider:** Groq
* **Model:** Select any current Llama-class model from the dropdown.
* **API Key:** Get a free key from console.groq.com.

*(If you need a backup, you can add Google Gemini or OpenRouter and select any current Flash or Haiku-class model as your #2 option).*

## Privacy & API Keys
Your API keys are stored securely in your browser's local storage (`localStorage`). They are never saved to the CRM database. When you process an email, the keys are sent temporarily to the backend to make the AI request, and then immediately discarded.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| **"Invalid JSON" / Empty extraction** | The AI model failed to format the contact properly. | Try switching to a smarter model (like a Haiku or Llama-70b class) in the AI Settings. |
| **"Server waking up — retry"** | The backend server was asleep. | Wait a few moments; the system automatically retries until the server wakes up. |
| **"RateLimitExceeded" / "HTTP 429"** | You are processing too many emails too quickly for your free API key. | Add a fallback provider in the AI Settings, or wait a minute before uploading more files. |
| **Timeout / "process failed"** | The AI took too long to read the email (over 45 seconds). | Use a faster provider like Groq, or process fewer emails at a time. |

## Screens
![Dashboard](docs/img/dashboard.png)
<!-- TODO: Add a screenshot of the main dashboard -->

![Upload Zone](docs/img/upload.png)
<!-- TODO: Add a screenshot of the EML drop zone -->

![AI Settings](docs/img/ai_settings.png)
<!-- TODO: Add a screenshot of the AI provider chain configuration -->

---
*Are you a developer? Read the [Developer Guide](docs/DEVELOPER.md) for local setup, architecture, and deployment instructions.*
