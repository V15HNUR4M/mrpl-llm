import re
from typing import Dict, Any, Optional

# Regular expressions for file formats
MD_KEYWORDS = [
    r"\bmarkdown\b",
    r"\.md\b",
    r"\bmd\s+file\b",
    r"\bmd\s+report\b",
    r"\bmd\s+document\b",
]

DOCX_KEYWORDS = [
    r"\bdocx\b",
    r"\.docx\b",
    r"\bword\s+doc\b",
    r"\bword\s+document\b",
    r"\bword\s+file\b",
    r"\bword\s+report\b",
    r"\bms\s+word\b",
    r"\bmicrosoft\s+word\b",
]

PDF_KEYWORDS = [
    r"\bpdf\b",
    r"\.pdf\b",
    r"\bpdf\s+file\b",
    r"\bpdf\s+report\b",
    r"\bpdf\s+document\b",
]

EXCEL_KEYWORDS = [
    r"\bexcel\b",
    r"\.xlsx\b",
    r"\bxlsx\b",
    r"\bspreadsheet\b",
    r"\bworkbook\b",
]

EXPORT_ACTION_KEYWORDS = [
    r"\bfile\b",
    r"\bdownload\b",
    r"\bdownloadable\b",
    r"\bexport\b",
    r"\bcreate\b",
    r"\bgenerate\b",
    r"\bgive\s+me\s+the\s+file\b",
    r"\bsave\s+as\b",
    r"\bproduce\b",
    r"\bbuild\b",
    r"\bmake\b",
]

EXCEL_MODIFY_KEYWORDS = [
    r"\bmodify\b",
    r"\bupdate\b",
    r"\bremove\s+duplicate",
    r"\bclean\b",
    r"\bfilter\s+and\s+save\b",
    r"\bwrite\b",
    r"\badd\s+formula\b",
]

def detect_file_generation_request(message: str) -> Dict[str, Any]:
    """
    Analyzes message to determine if a downloadable file was requested.
    Distinguishes document export (.md, .docx, .pdf) from Excel workbook creation/modification (.xlsx).
    Returns:
    {
        "requested": bool,
        "format": "markdown" | "docx" | "pdf" | "xlsx" | None,
        "action": "export" | "create" | "modify" | None,
        "is_excel_operation": bool
    }
    """
    default_result = {
        "requested": False,
        "format": None,
        "action": None,
        "is_excel_operation": False
    }

    text = message.strip().lower()
    if not text:
        return default_result

    # 1. Filter out purely educational/conceptual questions
    is_conceptual = re.search(
        r"^(what\s+is|how\s+to\s+write|explain\s+(?:the\s+)?(?:syntax|format|concept|definition)\s+of|give\s+me\s+a\s+general\s+explanation\s+of)\s+(markdown|docx|word|pdf|excel|spreadsheet|a\s+workbook)\??$",
        text,
        re.IGNORECASE
    )
    if is_conceptual:
        return default_result

    # Check for specific format keywords
    has_md = any(re.search(pat, text, re.IGNORECASE) for pat in MD_KEYWORDS)
    has_docx = any(re.search(pat, text, re.IGNORECASE) for pat in DOCX_KEYWORDS)
    has_pdf = any(re.search(pat, text, re.IGNORECASE) for pat in PDF_KEYWORDS)
    has_excel = any(re.search(pat, text, re.IGNORECASE) for pat in EXCEL_KEYWORDS)

    has_action = any(re.search(pat, text, re.IGNORECASE) for pat in EXPORT_ACTION_KEYWORDS)
    has_modify = any(re.search(pat, text, re.IGNORECASE) for pat in EXCEL_MODIFY_KEYWORDS)

    # 2. Excel Detection
    if has_excel:
        if has_modify:
            return {
                "requested": True,
                "format": "xlsx",
                "action": "modify",
                "is_excel_operation": True
            }
        if has_action or "report" in text or "table" in text:
            return {
                "requested": True,
                "format": "xlsx",
                "action": "create",
                "is_excel_operation": True
            }
        # If it's a data question on Excel without export wording (e.g. "which department spent the most in this excel?")
        return {
            "requested": False,
            "format": "xlsx",
            "action": "analyze",
            "is_excel_operation": True
        }

    # 3. Document Formats (.pdf, .docx, .md) require explicit export intent
    if has_pdf and (has_action or "report" in text):
        return {
            "requested": True,
            "format": "pdf",
            "action": "export",
            "is_excel_operation": False
        }

    if has_docx and (has_action or "report" in text or "document" in text):
        return {
            "requested": True,
            "format": "docx",
            "action": "export",
            "is_excel_operation": False
        }

    if has_md and has_action:
        return {
            "requested": True,
            "format": "markdown",
            "action": "export",
            "is_excel_operation": False
        }

    return default_result


def is_markdown_file_requested(message: str) -> bool:
    """
    Preserves exact backward-compatible behavior for markdown file requests.
    """
    res = detect_file_generation_request(message)
    return res["requested"] and res["format"] == "markdown"
