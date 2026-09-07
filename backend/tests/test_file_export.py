import pytest
import tempfile
import os
from app.services.file_export import (
    is_markdown_file_requested,
    sanitize_filename,
    derive_markdown_filename,
    GeneratedFileManager
)

def test_is_markdown_file_requested_positives():
    positive_prompts = [
        "Create this as a markdown file.",
        "Generate a downloadable .md report.",
        "Export this answer as Markdown.",
        "Create an MD file containing the summary.",
        "Create a Markdown report summarizing the infrastructure report and give me the file.",
        "Save this output as a .md file"
    ]
    for prompt in positive_prompts:
        assert is_markdown_file_requested(prompt) is True, f"Failed on: {prompt}"

def test_is_markdown_file_requested_negatives():
    negative_prompts = [
        "What is SRV-DB01?",
        "Summarize this report.",
        "What are the planned upgrades?",
        "How do I write markdown syntax?",
        "What is a markdown table?"
    ]
    for prompt in negative_prompts:
        assert is_markdown_file_requested(prompt) is False, f"Failed on: {prompt}"

def test_sanitize_filename():
    assert sanitize_filename("infrastructure-report.md") == "infrastructure-report.md"
    assert sanitize_filename("My Report") == "my-report.md"
    assert sanitize_filename("../../etc/passwd") == "etcpasswd.md"
    assert sanitize_filename("cool___file..md") == "cool-file.md"

def test_derive_markdown_filename():
    fn1 = derive_markdown_filename("Create a Markdown report summarizing the infrastructure report and give me the file.")
    assert fn1.endswith(".md")
    assert "infrastructure" in fn1

    fn2 = derive_markdown_filename("What is the storage capacity of SRV-DB01? Give me as markdown file")
    assert fn2.endswith(".md")
    assert "srv-db01" in fn2

@pytest.mark.asyncio
async def test_generated_file_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = GeneratedFileManager(storage_dir=tmpdir)
        content = "# System Report\n\n- Storage: 10TB\n- CPU: 95%"
        
        info = await mgr.save_markdown_file(
            owner_id="user-123",
            conversation_id="conv-456",
            filename="system-report.md",
            content=content
        )
        
        file_id = info["file_id"]
        assert info["filename"] == "system-report.md"
        assert info["size_bytes"] == len(content.encode("utf-8"))

        # Authorized owner lookup
        meta = await mgr.get_file_metadata(file_id, owner_id="user-123")
        assert meta is not None
        assert meta["filename"] == "system-report.md"

        # Unauthorized user lookup
        meta_denied = await mgr.get_file_metadata(file_id, owner_id="user-999")
        assert meta_denied is None

        # Verify content on disk is valid UTF-8
        path = mgr.get_file_path(file_id)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == content

        # Path traversal check
        with pytest.raises(ValueError):
            mgr._get_safe_path("../etc/passwd")
