import asyncio
import httpx
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
eml_content = b"To: test@example.com\nFrom: sender@example.com\nSubject: Test\n\nThis is a test email."

response = client.post(
    "/api/eml/process",
    files=[("files", ("test.eml", eml_content, "message/rfc822"))],
    data={"chain": "[]"}
)
print(response.status_code)
print(response.json())
