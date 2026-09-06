import asyncio
import httpx
import json
from app.main import app, lifespan
from app.core.config import settings

async def main():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post(f"{settings.API_V1_STR}/auth/register", json={"username": "debug_user", "password": "Password123!", "role": "OPERATOR"})
            login = await client.post(f"{settings.API_V1_STR}/auth/login", data={"username": "debug_user", "password": "Password123!"})
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            doc1 = "Boiler B301 inspection report: Operating pressure is 42.5 bar, steam temperature is 450 C. Normal operation."
            up1 = await client.post(
                f"{settings.API_V1_STR}/knowledge/documents",
                headers=headers,
                files={"file": ("Boiler_B301_Inspection.txt", doc1.encode("utf-8"), "text/plain")}
            )
            print("UP1 status:", up1.status_code, up1.json())

            doc2 = "Boiler B301 maintenance schedule: Next safety valve inspection due on 2026-11-15 by Team Delta."
            up2 = await client.post(
                f"{settings.API_V1_STR}/knowledge/documents",
                headers=headers,
                files={"file": ("Boiler_B301_Maintenance.txt", doc2.encode("utf-8"), "text/plain")}
            )
            print("UP2 status:", up2.status_code, up2.json())

            sr = await client.post(
                f"{settings.API_V1_STR}/knowledge/search",
                headers=headers,
                json={"query": "Boiler B301 inspection and maintenance schedule valve team", "top_k": 5}
            )
            print("Search status:", sr.status_code)
            print("Search json:", json.dumps(sr.json(), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
