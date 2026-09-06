import asyncio
import json
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def run_verification():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        # Login
        login_res = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create conversation
        conv_res = await client.post("/api/v1/conversations", json={"title": "Final Verification"}, headers=headers)
        assert conv_res.status_code in (200, 201)
        conv_id = conv_res.json()["id"]

        # QUERY 1: Live single-document
        q1 = "According to the Pump P204 inspection report, what abnormalities were identified, and what maintenance actions were recommended?"
        print("=== QUERY 1 ===")
        print(f"Query: {q1}")

        candidates_q1 = []
        answer_q1 = ""
        async with client.stream(
            "POST",
            "/api/v1/agents/general_agent/stream",
            json={"conversation_id": conv_id, "message": q1},
            headers=headers
        ) as resp:
            assert resp.status_code == 200
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    event_str, buf = buf.split("\n\n", 1)
                    for line in event_str.strip().split("\n"):
                        if line.startswith("data: "):
                            try:
                                ev = json.loads(line[6:])
                                if ev.get("type") == "context_candidate":
                                    candidates_q1.append(ev.get("candidate", {}))
                                elif ev.get("type") == "text_delta":
                                    answer_q1 += ev.get("text", "")
                            except Exception:
                                pass

        print(f"\nCandidates retrieved count: {len(candidates_q1)}")
        for i, c in enumerate(candidates_q1):
            fn = c.get("metadata", {}).get("filename")
            sc = c.get("relevance_score")
            ct = c.get("type")
            print(f"  Candidate {i+1}: file={fn}, score={sc}, type={ct}")
        print("\n--- ACTUAL MODEL ANSWER Q1 ---")
        print(answer_q1.strip())
        print("--- END ANSWER Q1 ---\n")

        # QUERY 2: Live cross-document
        q2 = "Compare the Pump P204 inspection findings from August 18 with the maintenance performed on August 20. Which issues were addressed, which remained unresolved, and what follow-up was recommended?"
        print("=== QUERY 2 ===")
        print(f"Query: {q2}")

        candidates_q2 = []
        answer_q2 = ""
        async with client.stream(
            "POST",
            "/api/v1/agents/general_agent/stream",
            json={"conversation_id": conv_id, "message": q2},
            headers=headers
        ) as resp:
            assert resp.status_code == 200
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    event_str, buf = buf.split("\n\n", 1)
                    for line in event_str.strip().split("\n"):
                        if line.startswith("data: "):
                            try:
                                ev = json.loads(line[6:])
                                if ev.get("type") == "context_candidate":
                                    candidates_q2.append(ev.get("candidate", {}))
                                elif ev.get("type") == "text_delta":
                                    answer_q2 += ev.get("text", "")
                            except Exception:
                                pass

        print(f"\nCandidates retrieved count: {len(candidates_q2)}")
        for i, c in enumerate(candidates_q2):
            fn = c.get("metadata", {}).get("filename")
            sc = c.get("relevance_score")
            ct = c.get("type")
            print(f"  Candidate {i+1}: file={fn}, score={sc}, type={ct}")
        print("\n--- ACTUAL MODEL ANSWER Q2 ---")
        print(answer_q2.strip())
        print("--- END ANSWER Q2 ---\n")

if __name__ == "__main__":
    asyncio.run(run_verification())
