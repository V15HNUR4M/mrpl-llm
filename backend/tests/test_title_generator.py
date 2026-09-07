import pytest
from app.services.title_generator import generate_title_heuristic, generate_title

def test_title_heuristic_user_examples():
    # Example 1
    t1 = generate_title_heuristic("What is the storage capacity of SRV-DB01?")
    assert t1 == "SRV-DB01 Storage Capacity"
    assert 3 <= len(t1.split()) <= 7

    # Example 2
    t2 = generate_title_heuristic("Summarize the infrastructure report")
    assert t2 == "Infrastructure Report Summary"
    assert 3 <= len(t2.split()) <= 7

    # Example 3
    t3 = generate_title_heuristic("What are the planned upgrades for 2026?")
    assert t3 == "2026 Planned Upgrades"
    assert 3 <= len(t3.split()) <= 7

def test_title_heuristic_word_limits_and_fillers():
    # Fluff stripping
    t = generate_title_heuristic("Can you please tell me about pump maintenance logs?")
    assert "Pump Maintenance" in t
    words = t.split()
    assert 3 <= len(words) <= 7

    # Empty string fallback
    assert generate_title_heuristic("") == "New Conversation"

@pytest.mark.asyncio
async def test_generate_title_fallback():
    # With no gateway, gracefully returns heuristic
    title = await generate_title("What is the storage capacity of SRV-DB01?", gateway=None)
    assert title == "SRV-DB01 Storage Capacity"
