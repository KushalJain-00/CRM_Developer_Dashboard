import sys
import os
import asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from supabase import create_client, Client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from db.database import AsyncSessionLocal

async def clear_db():
    print("Clearing main CRM database...")
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE TABLE call_logs CASCADE;"))
        await db.execute(text("TRUNCATE TABLE contacts CASCADE;"))
        await db.execute(text("TRUNCATE TABLE companies CASCADE;"))
        await db.execute(text("TRUNCATE TABLE session_data CASCADE;"))
        await db.commit()
    print("CRM database cleared successfully!")

    print("Clearing EML Staging area (Supabase)...")
    url = os.getenv("EML_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    key = os.getenv("EML_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if url and key:
        sb = create_client(url, key)
        # Supabase API doesn't support TRUNCATE directly from client, so we do DELETE with filter
        # It has a limit on rows, but let's delete anything with an id
        try:
            # neq id to some impossible UUID or empty string to match all
            res1 = sb.table("eml_contacts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            res2 = sb.table("eml_emails").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            print(f"Cleared EML staging area. Deleted {len(res1.data)} contacts and {len(res2.data)} emails.")
        except Exception as e:
            print(f"Error clearing Supabase: {e}")
    else:
        print("Supabase credentials not found, skipping EML staging clear.")

if __name__ == "__main__":
    asyncio.run(clear_db())
