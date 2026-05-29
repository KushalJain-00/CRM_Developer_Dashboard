from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    'postgresql+asyncpg://user:pass@host/db',
    prepared_statement_cache_size=0,
    connect_args={
        "statement_cache_size": 0
    }
)
print("Engine created successfully")
