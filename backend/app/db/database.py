import sqlite3
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import event
from sqlalchemy.pool import NullPool

from app.core.config import settings

from sqlalchemy.engine import Engine

# WAL mode and foreign keys for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()

import os

# Ensure parent directory of SQLite database exists
if settings.SQLITE_URL.startswith("sqlite"):
    db_path = settings.SQLITE_URL.split(":///")[-1]
    if db_path and not db_path.startswith(":memory:"):
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

engine = create_async_engine(
    settings.SQLITE_URL,
    echo=False,
    # NullPool is often recommended for async sqlite to avoid thread-sharing issues
    poolclass=NullPool 
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
