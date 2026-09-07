import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-12345-67890-test-dev")
os.environ.setdefault("ENVIRONMENT", "testing")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.database import Base, engine

def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as asyncio")

from app.main import app, lifespan

@pytest_asyncio.fixture(autouse=True)
async def app_lifespan():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    async with lifespan(app):
        yield
        
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
