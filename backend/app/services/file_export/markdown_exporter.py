from typing import Optional

def export_to_markdown(content: str, title: Optional[str] = None) -> bytes:
    """
    Exports clean Markdown content as UTF-8 bytes.
    Optionally prepends title if not already present.
    """
    cleaned = content.strip()
    if title and not cleaned.startswith("# "):
        cleaned = f"# {title}\n\n{cleaned}"
    return cleaned.encode("utf-8")
