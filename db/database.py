from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./crm.db").strip().strip('"').strip("'")

# Supabase gives "postgres://..." but SQLAlchemy async requires "postgresql+asyncpg://..."
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Configure engine based on database type
if DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL (Supabase) — use connection pooling for production
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,       # auto-reconnect on stale connections
        pool_recycle=300,         # recycle connections every 5 min
        connect_args={
            "prepared_statement_cache_size": 0,  # Required for Supabase pgbouncer (transaction mode)
        }
    )

AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

Base = declarative_base()


async def get_db():
    """Dependency for FastAPI routes to get async database session"""
    async with AsyncSessionLocal() as db:
        yield db


async def init_db():
    """Initialize database - create all tables asynchronously"""
    from db import models  # noqa
    from sqlalchemy import text
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Dynamically add the files column if it doesn't exist to support existing DBs
        try:
            await conn.execute(text("ALTER TABLE contacts ADD COLUMN files TEXT"))
        except Exception:
            # Column likely already exists
            pass
