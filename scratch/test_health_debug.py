import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath("."))
os.environ["SECRET_KEY"] = "test-secret-key-12345-67890-test-dev"
os.environ["ENVIRONMENT"] = "development"

from app.core.observability.service import get_observability_service
from app.api.v1.endpoints.health import check_database_readiness

async def main():
    service = get_observability_service()
    h = await service.get_health()
    print("Observability get_health():", h.model_dump())
    db_ok, db_status = await check_database_readiness()
    print("Health check_database_readiness():", db_ok, db_status)

if __name__ == "__main__":
    asyncio.run(main())
