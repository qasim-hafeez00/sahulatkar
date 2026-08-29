from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings


# BUG FIX (found live-running the real order flow end-to-end): unlike every
# other service, ledger-service creates its own engine here instead of using
# packages/shared-python/sk_shared/database.py's (which already sets
# statement_cache_size=0 for exactly this reason). DATABASE_URL routes
# through PgBouncer in transaction-pool mode (see PGBOUNCER_POOL_MODE in
# infra/docker/docker-compose.yml) -- PgBouncer can hand a single logical
# asyncpg connection different backend Postgres connections between
# statements, so asyncpg's client-side prepared-statement cache (keyed by
# name, not content) can collide with whatever the previous backend
# connection already had prepared under the same name. Live-verified: this
# made src/events/listener.py's real financial event processing (down
# payment confirmation, installment payment, late fee) fail unpredictably
# with `asyncpg.exceptions.DuplicatePreparedStatementError` on ANY query --
# not classified as a transient error by `_is_transient_error`, so the event
# was dropped rather than retried, meaning ledger postings for real money
# movement could silently never happen. Disabling the client-side prepared
# statement cache (the documented fix for exactly this PgBouncer/asyncpg
# incompatibility) makes every query a fresh unnamed statement, immune to
# this class of failure regardless of which backend PgBouncer routes to.
engine = create_async_engine(settings.database_url, echo=False, connect_args={"statement_cache_size": 0})
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session