import asyncio
import json
import sqlite3
import chromadb
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def run_stale_data_test():
    print("=" * 70)
    print("STALE-DATA VERIFICATION: COMPLETE DELETION AND UNLEARNING TEST")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # Step 1: Login
        print("\n1. Logging in as admin...")
        login_res = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("-> Logged in successfully.")

        # Step 2: List current documents
        print("\n2. Fetching documents before deletion...")
        docs_res = await client.get("/api/v1/knowledge/documents", headers=headers)
        assert docs_res.status_code == 200
        docs = docs_res.json()
        print(f"-> Found {len(docs)} documents:")
        for d in docs:
            print(f"   - {d['filename']} (ID: {d['id']})")

        # Step 3: Delete both documents
        print("\n3. Deleting both reports via DELETE /api/v1/knowledge/documents/{id}...")
        deletion_results = {}
        for d in docs:
            if d["filename"] in ("Pump_P204_Inspection_Report.txt", "Pump_P204_Maintenance_Report.txt"):
                del_res = await client.delete(f"/api/v1/knowledge/documents/{d['id']}", headers=headers)
                print(f"   - DELETE {d['filename']} ({d['id']}): HTTP {del_res.status_code} {del_res.text}")
                deletion_results[d["filename"]] = del_res.status_code == 200

        # Step 4: Verify Knowledge Base API
        print("\n4. Verifying Knowledge Base API after deletion...")
        docs_after = (await client.get("/api/v1/knowledge/documents", headers=headers)).json()
        remaining_filenames = [d["filename"] for d in docs_after]
        print(f"-> Remaining in Knowledge Base: {remaining_filenames}")
        kb_empty = "Pump_P204_Inspection_Report.txt" not in remaining_filenames and "Pump_P204_Maintenance_Report.txt" not in remaining_filenames

        # Step 5: Verify SQLite Database State
        print("\n5. Verifying SQLite database state...")
        conn = sqlite3.connect("./backend/data/mrpl.db")
        c = conn.cursor()
        doc_rows = c.execute(
            "SELECT id, filename FROM documents WHERE filename IN ('Pump_P204_Inspection_Report.txt', 'Pump_P204_Maintenance_Report.txt')"
        ).fetchall()
        print(f"-> SQLite documents matching target filenames: {len(doc_rows)} rows: {doc_rows}")
        version_rows = c.execute("SELECT count(*) FROM document_versions").fetchone()[0]
        chunk_rows = c.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
        print(f"-> SQLite total remaining versions: {version_rows}, chunks: {chunk_rows}")
        db_cleaned = len(doc_rows) == 0 and version_rows == 0 and chunk_rows == 0
        conn.close()

        # Step 6: Verify Chroma Vector Store State
        print("\n6. Verifying Chroma vector store state...")
        chroma_client = chromadb.PersistentClient(path="./backend/data/chroma")
        coll = chroma_client.get_collection("mrpl_knowledge")
        total_vectors = coll.count()
        inspect_vectors = coll.get(where={"filename": "Pump_P204_Inspection_Report.txt"})
        maint_vectors = coll.get(where={"filename": "Pump_P204_Maintenance_Report.txt"})
        print(f"-> Chroma total vectors: {total_vectors}")
        print(f"-> Chroma vectors for Inspection Report: {len(inspect_vectors['ids'])}")
        print(f"-> Chroma vectors for Maintenance Report: {len(maint_vectors['ids'])}")
        vector_cleaned = (len(inspect_vectors['ids']) == 0 and len(maint_vectors['ids']) == 0 and total_vectors == 0)

        # Step 7: Verify Search API returns 0 results
        print("\n7. Verifying /api/v1/knowledge/search returns 0 results...")
        search_res = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "Pump P204 inspection date", "top_k": 10},
            headers=headers
        )
        search_items = search_res.json()
        print(f"-> Search results count: {len(search_items)}")
        search_clean = len(search_items) == 0

        # Step 8: Start a completely NEW conversation
        print("\n8. Creating a completely NEW conversation...")
        new_conv_res = await client.post(
            "/api/v1/conversations",
            json={"title": "Post-Deletion Clean Test"},
            headers=headers
        )
        assert new_conv_res.status_code in (200, 201)
        new_conv_id = new_conv_res.json()["id"]
        print(f"-> New conversation ID: {new_conv_id}")

        # Step 9: Ask the exact inspection date question in NEW chat
        q_exact = "What was the inspection date recorded in the Pump P204 inspection report?"
        print(f"\n9. Asking in NEW chat:\n   '{q_exact}'")

        candidates_received = []
        actual_response = ""
        async with client.stream(
            "POST",
            "/api/v1/agents/general_agent/stream",
            json={"conversation_id": new_conv_id, "message": q_exact},
            headers=headers
        ) as stream_resp:
            assert stream_resp.status_code == 200
            buf = ""
            async for chunk in stream_resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    ev_str, buf = buf.split("\n\n", 1)
                    for line in ev_str.strip().split("\n"):
                        if line.startswith("data: "):
                            try:
                                ev = json.loads(line[6:])
                                if ev.get("type") == "context_candidate":
                                    candidates_received.append(ev.get("candidate", {}))
                                elif ev.get("type") == "text_delta":
                                    actual_response += ev.get("text", "")
                            except Exception:
                                pass

        print(f"\n-> Candidates retrieved in new chat: {len(candidates_received)}")
        print("\n--- ACTUAL MODEL RESPONSE ---")
        print(actual_response.strip())
        print("--- END ACTUAL RESPONSE ---\n")

        # Step 10: Analyze response for unlearning
        ans_lower = actual_response.lower()
        contains_fabricated_date = "2026-08-18" in actual_response or "august 18" in ans_lower or "august 18, 2026" in ans_lower
        states_lack_of_info = any(neg in ans_lower for neg in [
            "not", "does not contain", "no information", "don't have", "unmentioned", "unavailable", "cannot find", "no context", "not mentioned"
        ])

        print("=" * 70)
        print("VERIFICATION RESULTS SUMMARY:")
        print(f"1. Deletion Results: {deletion_results}")
        print(f"2. KB Clean: {kb_empty}")
        print(f"3. DB Cleaned: {db_cleaned}")
        print(f"4. Vector Store Cleaned: {vector_cleaned}")
        print(f"5. Search Endpoint Clean: {search_clean}")
        print(f"6. Candidates in New Chat: {len(candidates_received)}")
        print(f"7. Fabricated '2026-08-18' Date Present: {contains_fabricated_date}")
        print(f"8. States Lack of Knowledge: {states_lack_of_info}")
        print("=" * 70)

        # Assertions
        assert kb_empty, "Documents still present in Knowledge Base list"
        assert db_cleaned, "Database still contains document records"
        assert vector_cleaned, "Chroma still contains vectors for deleted documents"
        assert search_clean, "Search endpoint returned results for deleted documents"
        assert len(candidates_received) == 0, "New chat retrieved candidates for deleted documents"
        assert not contains_fabricated_date, "Model hallucinated/remembered the deleted inspection date '2026-08-18'!"
        assert states_lack_of_info, "Model did not state lack of information"

        print("\nALL STALE-DATA CHECKS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_stale_data_test())
