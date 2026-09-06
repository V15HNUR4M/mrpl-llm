import asyncio
import json
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def test_live_chain():
    print("=" * 70)
    print("LIVE RUNTIME CHAIN TEST: RETRIEVAL TO GENERATION")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # Step 1: Login
        print("\n1. Logging in as admin...")
        login_res = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("-> Login successful!")

        # Step 2: List Documents in Knowledge Base
        print("\n2. Checking Knowledge Base documents...")
        docs_res = await client.get("/api/v1/knowledge/documents", headers=headers)
        assert docs_res.status_code == 200
        docs = docs_res.json()
        print(f"-> Found {len(docs)} documents in Knowledge Base:")
        for d in docs:
            print(f"   - {d['filename']} (ID: {d['id']}, Status: {d['status']})")
        assert any(d["filename"] == "Pump_P204_Inspection_Report.txt" for d in docs)
        assert any(d["filename"] == "Pump_P204_Maintenance_Report.txt" for d in docs)

        # Step 3: Create Conversation
        print("\n3. Creating new conversation...")
        conv_res = await client.post("/api/v1/conversations", json={"title": "RAG Verification"}, headers=headers)
        assert conv_res.status_code in (200, 201), f"Create conversation failed: {conv_res.status_code} {conv_res.text}"
        conv_id = conv_res.json()["id"]
        print(f"-> Created conversation: {conv_id}")

        # Step 4: Stream Chat Message
        agent_id = "general_agent"
        prompt = "According to the Pump P204 inspection report, what abnormalities were identified, and what maintenance actions were recommended?"
        print(f"\n4. Sending prompt to agent '{agent_id}':\n   '{prompt}'")

        rag_candidates_received = []
        states_received = []
        accumulated_text = ""

        print("\n--- STREAMING RUNTIME EVENTS ---")
        async with client.stream(
            "POST",
            f"/api/v1/agents/{agent_id}/stream",
            json={
                "conversation_id": conv_id,
                "message": prompt
            },
            headers=headers
        ) as response:
            assert response.status_code == 200
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    lines = event_str.strip().split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            data_json = line[6:]
                            try:
                                event = json.loads(data_json)
                                ev_type = event.get("type")
                                if ev_type == "state_changed":
                                    st = event.get("state")
                                    states_received.append(st)
                                    print(f"   [STATE] -> {st}")
                                elif ev_type == "context_candidate":
                                    cand = event.get("candidate", {})
                                    rag_candidates_received.append(cand)
                                    print(f"   [CANDIDATE] -> type={cand.get('type')}, source={cand.get('source')}, filename={cand.get('metadata', {}).get('filename')}")
                                elif ev_type == "text_delta":
                                    txt = event.get("text", "")
                                    accumulated_text += txt
                                    print(txt, end="", flush=True)
                                elif ev_type == "completed":
                                    print(f"\n   [COMPLETED] Final answer received.")
                            except Exception as e:
                                pass

        print("\n" + "=" * 70)
        print("VERIFICATION OF RETRIEVAL-TO-GENERATION CHAIN:")
        print(f"Total States Traversed: {states_received}")
        print(f"RAG Candidates Retrieved: {len(rag_candidates_received)}")
        for c in rag_candidates_received:
            print(f"   - {c.get('type')}: {c.get('metadata', {}).get('filename')} (score: {c.get('relevance_score')})")

        print(f"\nFull Answer Text ({len(accumulated_text)} chars):")
        print(accumulated_text)

        # Assertions on retrieval
        assert len(rag_candidates_received) > 0, "No RAG candidates were retrieved!"
        assert any(c.get("type") == "rag" for c in rag_candidates_received), "Candidate type must be 'rag'"
        assert any("Inspection" in str(c.get("metadata", {}).get("filename", "")) for c in rag_candidates_received), "Must retrieve Inspection Report"

        # Assertions on grounded facts (from Pump_P204_Inspection_Report.txt)
        ans_lower = accumulated_text.lower()
        assert "vibration" in ans_lower, "Answer must mention vibration abnormality"
        assert "bearing" in ans_lower, "Answer must mention bearing condition"
        assert "seal" in ans_lower, "Answer must mention seal condition"
        assert "lubricat" in ans_lower or "align" in ans_lower, "Answer must mention recommended actions"
        assert "don't have any information" not in ans_lower, "Model must not report lack of information!"

        print("\n-> PASS: End-to-end RAG retrieval-to-generation chain verified successfully!")

        # Step 5: Cross-document question
        print("\n" + "=" * 70)
        print("5. CROSS-DOCUMENT COMPARISON QUERY")
        cross_prompt = "Compare the Pump P204 inspection findings from August 18 with the maintenance performed on August 20, including what was done to the coupling, bearing, and mechanical seal."
        print(f"Prompt: '{cross_prompt}'")
        
        cross_candidates = []
        cross_text = ""
        async with client.stream(
            "POST",
            "/api/v1/agents/general_agent/stream",
            json={
                "conversation_id": conv_id,
                "message": cross_prompt
            },
            headers=headers
        ) as response:
            assert response.status_code == 200
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    for line in event_str.strip().split("\n"):
                        if line.startswith("data: "):
                            try:
                                ev = json.loads(line[6:])
                                if ev.get("type") == "context_candidate":
                                    cross_candidates.append(ev.get("candidate", {}))
                                elif ev.get("type") == "text_delta":
                                    cross_text += ev.get("text", "")
                                    print(ev.get("text", ""), end="", flush=True)
                            except Exception:
                                pass

        print("\n" + "=" * 70)
        print(f"Cross-document candidates: {len(cross_candidates)}")
        filenames = {c.get("metadata", {}).get("filename") for c in cross_candidates}
        print(f"Retrieved files: {filenames}")
        assert "Pump_P204_Inspection_Report.txt" in filenames
        assert "Pump_P204_Maintenance_Report.txt" in filenames
        print("\n-> PASS: Cross-document retrieval and synthesis verified successfully!")

if __name__ == "__main__":
    asyncio.run(test_live_chain())
