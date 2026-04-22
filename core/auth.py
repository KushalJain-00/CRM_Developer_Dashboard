from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
import os

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: str = Security(api_key_header)):
    expected = os.getenv("API_KEY", "")
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key is not configured on the server")
    if key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return True
