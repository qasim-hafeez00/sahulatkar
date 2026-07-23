from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sk_app:localdev123@localhost:5432/sahulatkar")

engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"statement_cache_size": 0})
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session
