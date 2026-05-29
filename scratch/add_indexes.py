import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Ensure we use asyncpg driver
db_url = os.environ.get('DATABASE_URL', '')
if db_url.startswith('postgresql://'):
    db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)

async def add_indexes():
    print(f"Connecting to {db_url}")
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            print("Adding index on records.session_id...")
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_records_session_id ON records (session_id);"))
            print("Adding index on call_logs.contact_id...")
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_logs_contact_id ON call_logs (contact_id);"))
            print("Adding index on call_logs.company_id...")
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_call_logs_company_id ON call_logs (company_id);"))
            print("Indexes added successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_indexes())
