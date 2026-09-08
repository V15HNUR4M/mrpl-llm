import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

def login(username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{BASE_URL}/auth/login", data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]

def get_me(token):
    req = urllib.request.Request(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get_conversations(token):
    req = urllib.request.Request(f"{BASE_URL}/conversations", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        return res.get("items", res) if isinstance(res, dict) else res

def create_conversation(token, title="New Conversation"):
    data = json.dumps({"title": title}).encode()
    req = urllib.request.Request(f"{BASE_URL}/conversations", data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get_messages(token, conv_id):
    req = urllib.request.Request(f"{BASE_URL}/conversations/{conv_id}/messages", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        return res.get("items", res) if isinstance(res, dict) else res

def stream_chat(token, conv_id, message):
    data = json.dumps({"conversation_id": conv_id, "message": message}).encode()
    req = urllib.request.Request(f"{BASE_URL}/agents/general_agent/stream", data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    events = []
    text_deltas = []
    with urllib.request.urlopen(req, timeout=60) as resp:
        for line in resp:
            line = line.decode().strip()
            if line.startswith("data:"):
                ev = json.loads(line[5:].strip())
                events.append(ev)
                if ev.get("type") == "text_delta":
                    text_deltas.append(ev.get("text", ""))
    return events, "".join(text_deltas)

def test_a_admin_chat(admin_token):
    print("\n--- TEST A: ADMIN CHAT ---")
    admin_conv = create_conversation(admin_token, "Admin Test A")
    events, full_text = stream_chat(admin_token, admin_conv["id"], "Reply with exactly: MRPL USER TEST")
    print(f"Admin streamed text: {full_text!r}")
    assert "MRPL USER TEST" in full_text, f"Admin reply mismatch: {full_text}"
    messages = get_messages(admin_token, admin_conv["id"])
    assert len(messages) >= 2, f"Expected user + assistant messages, got {len(messages)}"
    print("[PASS] Test A: Admin chat works and persists.")

def test_b_fresh_user_chat(user_token):
    print("\n--- TEST B: FRESH USER CHAT ---")
    user_me = get_me(user_token)
    print(f"User identity: username={user_me['username']}, id={user_me['id']}, role={user_me['role']}")
    assert user_me["role"] == "USER"
    
    convs = get_conversations(user_token)
    print(f"User existing conversation count: {len(convs)}")
    
    new_conv = create_conversation(user_token, "Engineer Verify Fresh Chat")
    assert new_conv["user_id"] == user_me["id"]
    
    events, full_text = stream_chat(user_token, new_conv["id"], "Reply with exactly: MRPL USER TEST")
    print(f"User streamed text: {full_text!r}")
    assert "MRPL USER TEST" in full_text, f"User reply mismatch: {full_text}"
    
    messages = get_messages(user_token, new_conv["id"])
    print(f"Messages in user conv: {len(messages)}")
    assert len(messages) >= 2, f"Expected user + assistant messages, got {len(messages)}"
    assistant_msg = [m for m in messages if m["role"] == "assistant"][0]
    assert "MRPL USER TEST" in assistant_msg["content"]
    print("[PASS] Test B: Fresh user chat generated and persisted under engineer_verify.")

def test_e_backend_security_cross_user_block(admin_token, user_token):
    print("\n--- TEST E: BACKEND SECURITY (CROSS-USER CONVERSATION ACCESS) ---")
    admin_conv = create_conversation(admin_token, "Secret Admin Conv")
    
    # Attempt 1: engineer_verify reading admin's messages
    try:
        get_messages(user_token, admin_conv["id"])
        assert False, "Security failure: user was able to read admin messages!"
    except urllib.error.HTTPError as he:
        print(f"Attempting to read admin messages with user token: HTTP {he.code} (Expected 404/403)")
        assert he.code in (403, 404), f"Unexpected code: {he.code}"

    # Attempt 2: engineer_verify sending stream request using admin's conversation_id
    data = json.dumps({"conversation_id": admin_conv["id"], "message": "Malicious Prompt"}).encode()
    req = urllib.request.Request(f"{BASE_URL}/agents/general_agent/stream", data=data, headers={
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    })
    try:
        urllib.request.urlopen(req)
        assert False, "Security failure: user was able to stream to admin conversation!"
    except urllib.error.HTTPError as he:
        print(f"Attempting to stream with admin conv_id using user token: HTTP {he.code} (Expected 404/403)")
        assert he.code in (403, 404), f"Unexpected code: {he.code}"
        
    print("[PASS] Test E: Backend security strictly rejected cross-user conversation access.")

def test_f_active_generation_endpoint(admin_token):
    print("\n--- TEST F: ACTIVE GENERATION ENDPOINT ---")
    # When no active generation exists
    req = urllib.request.Request(f"{BASE_URL}/agents/generations/active", headers={"Authorization": f"Bearer {admin_token}"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        print("Active gen when none running:", res)
        assert res["active"] is False
        assert res["generation"] is None
    print("[PASS] Test F: Active generation endpoint returns valid structure.")

def main():
    admin_token = login("admin", "ProductionAdmin2026!Secure")
    user_token = login("engineer_verify", "Password123!")

    test_a_admin_chat(admin_token)
    test_b_fresh_user_chat(user_token)
    test_e_backend_security_cross_user_block(admin_token, user_token)
    test_f_active_generation_endpoint(admin_token)
    print("\n=======================================================")
    print("ALL API-LEVEL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")

if __name__ == "__main__":
    main()
