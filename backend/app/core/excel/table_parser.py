import re
import csv
import io
from typing import List, Tuple, Any, Optional, Dict


def clean_cell_str(s: str) -> str:
    """Removes leftover markdown formatting, pipes, and surrounding whitespace."""
    if not s:
        return ""
    s = s.strip()
    # Strip leading/trailing pipes if present on individual cells
    s = re.sub(r"^\|+|\|+$", "", s).strip()
    # Strip markdown bold/italic/code syntax: **val**, *val*, `val`
    s = re.sub(r"^\*{1,2}(.*?)\*{1,2}$", r"\1", s).strip()
    s = re.sub(r"^_{1,2}(.*?)_{1,2}$", r"\1", s).strip()
    s = re.sub(r"^`+(.*?)`+$", r"\1", s).strip()
    return s


def coerce_value(val: Any) -> Any:
    """Converts numeric strings to int or float and cleans markdown text."""
    if val is None:
        return ""
    if isinstance(val, (int, float, bool)):
        return val

    s = clean_cell_str(str(val))
    if not s:
        return ""

    # Check boolean
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False

    # Check integer (e.g. 10, -5, +3)
    if re.match(r"^[+-]?\d+$", s):
        try:
            return int(s)
        except ValueError:
            pass

    # Check float (e.g. 12.5, -0.75)
    if re.match(r"^[+-]?\d+\.\d+$", s):
        try:
            return float(s)
        except ValueError:
            pass

    # Check numbers with commas (e.g. 1,250 or 1,250.50)
    if re.match(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$", s):
        try:
            clean_s = s.replace(",", "")
            return float(clean_s) if "." in clean_s else int(clean_s)
        except ValueError:
            pass

    return s


def is_markdown_separator_row(cells: List[str]) -> bool:
    """Returns True if the row is purely markdown alignment/divider syntax, e.g. | --- | :---: |"""
    if not cells:
        return False
    non_empty = [c for c in cells if c.strip()]
    if not non_empty:
        return True
    return all(re.match(r"^:?-+:?$", c.strip()) for c in non_empty)


def parse_markdown_table(text: str) -> Tuple[List[str], List[List[Any]]]:
    """
    Parses Markdown tables into clean headers and typed rows.
    Removes all delimiter characters (| and ---) and extracts real columns.
    """
    lines = text.strip().splitlines()
    table_lines = []

    for line in lines:
        stripped = line.strip()
        # Look for table lines that have pipe separators
        if "|" in stripped:
            table_lines.append(stripped)
        elif table_lines:
            # End of table block encountered
            break

    if not table_lines:
        return [], []

    # Parse rows by splitting on '|'
    parsed_rows = []
    for line in table_lines:
        parts = line.split("|")
        # Markdown tables typically start and end with '|', leaving empty strings on edges
        if parts and not parts[0].strip():
            parts = parts[1:]
        if parts and not parts[-1].strip():
            parts = parts[:-1]

        cleaned_parts = [clean_cell_str(p) for p in parts]
        if cleaned_parts and not is_markdown_separator_row(cleaned_parts):
            parsed_rows.append(cleaned_parts)

    if not parsed_rows:
        return [], []

    # First row is headers
    headers = [clean_cell_str(h) for h in parsed_rows[0]]
    headers = [h if h else f"Column_{i+1}" for i, h in enumerate(headers)]

    # Remaining rows are data rows
    data_rows = []
    for row in parsed_rows[1:]:
        typed_row = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else ""
            typed_row.append(coerce_value(val))
        data_rows.append(typed_row)

    return headers, data_rows


def parse_bulleted_table(text: str) -> Tuple[List[str], List[List[Any]]]:
    """
    Parses bulleted structured text formatted as:
    Headers:
    - Col1
    - Col2
    - Col3
    
    Rows:
    - Department: Sales
      - Employee Count: 100
      - Budget: 50.0
    """
    headers_match = re.search(r"(?:Headers|Columns):\s*\n((?:[ \t]*[-*•]\s*[^\n]+\n?)+)", text, re.IGNORECASE)
    if not headers_match:
        return [], []
    
    headers_raw = re.findall(r"[-*•]\s*([^\n]+)", headers_match.group(1))
    headers = [clean_cell_str(h) for h in headers_raw if h.strip()]
    if not headers:
        return [], []

    rows_match = re.search(r"(?:Rows|Sample Data|Data):\s*\n([\s\S]+)", text, re.IGNORECASE)
    if not rows_match:
        return [], []

    rows_text = rows_match.group(1).strip()
    # Split on lines starting with a top-level bullet (e.g. "- " at line start)
    raw_blocks = [b.strip() for b in re.split(r"(?:^|\n)(?:[-*•]\s+)", rows_text) if b.strip()]
    
    data_rows = []
    for block in raw_blocks:
        row_dict = {}
        sub_items = []
        for line in block.splitlines():
            line_str = clean_cell_str(line)
            if ":" in line_str:
                k, v = line_str.split(":", 1)
                k_clean = clean_cell_str(k).lower()
                v_clean = clean_cell_str(v)
                row_dict[k_clean] = coerce_value(v_clean)
                sub_items.append(coerce_value(v_clean))
            elif line_str:
                sub_items.append(coerce_value(line_str))

        if row_dict:
            row_vals = []
            for h in headers:
                h_low = h.lower()
                matched_val = None
                for k, v in row_dict.items():
                    if k in h_low or h_low in k:
                        matched_val = v
                        break
                if matched_val is None and len(sub_items) > len(row_vals):
                    matched_val = sub_items[len(row_vals)]
                row_vals.append(matched_val)
            data_rows.append(row_vals)
        elif len(sub_items) >= len(headers):
            data_rows.append(sub_items[:len(headers)])

    if headers and data_rows:
        return headers, data_rows

    return [], []


def parse_csv_or_tsv_block(text: str) -> Tuple[List[str], List[List[Any]]]:
    """Parses code blocks containing CSV or TSV data."""
    match = re.search(r"```(?:csv|tsv)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return [], []
    content = match.group(1).strip()

    for delimiter in ["\t", ","]:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = [r for r in reader if any(cell.strip() for cell in r)]
        if len(rows) >= 2 and len(rows[0]) >= 2:
            headers = [clean_cell_str(h) for h in rows[0]]
            data_rows = [[coerce_value(cell) for cell in r] for r in rows[1:]]
            return headers, data_rows

    return [], []


def extract_tabular_data(
    text: str,
    session_events: Optional[List[Dict[str, Any]]] = None,
    user_input: Optional[str] = None
) -> Tuple[List[str], List[List[Any]]]:
    """
    Extracts tabular data for Excel generation.
    1. First checks session_events for structured Python tool data.
    2. Parses Markdown tables from text.
    3. Parses bulleted table structures (Headers: / Rows:).
    4. Parses CSV/TSV blocks from text.
    5. Aligns with explicit user prompt columns if specified.
    """
    # 1. Prefer structured Python data if available in session events
    if session_events:
        for event in session_events:
            tool_name = event.get("tool") or ""
            args = event.get("arguments") or {}
            result = event.get("result") or {}

            if tool_name == "create_workbook" and args.get("headers") and args.get("rows"):
                cleaned_headers = [clean_cell_str(h) for h in args["headers"]]
                cleaned_rows = [[coerce_value(cell) for cell in row] for row in args["rows"]]
                return cleaned_headers, cleaned_rows

            if tool_name == "filter_rows" and isinstance(result, dict) and result.get("filtered_rows"):
                cols = [clean_cell_str(c) for c in result.get("columns", [])]
                if cols:
                    data = [[coerce_value(cell) for cell in row] for row in result["filtered_rows"]]
                    return cols, data

            if tool_name == "aggregate_data" and isinstance(result, dict) and result.get("grouped_aggregates"):
                group_col = clean_cell_str(result.get("group_by", "Category"))
                agg_col = clean_cell_str(f"{result.get('operation', 'Total')}_{result.get('column', 'Value')}")
                headers = [group_col, agg_col]
                data = [[coerce_value(item.get("group")), coerce_value(item.get("value"))] for item in result["grouped_aggregates"]]
                return headers, data

    # 2. Parse Markdown table from text
    headers, rows = parse_markdown_table(text)
    if headers and rows:
        return headers, rows

    # 3. Parse bulleted table structure (Headers: ... Rows: ...)
    headers, rows = parse_bulleted_table(text)
    if headers and rows:
        return headers, rows

    # 4. Parse CSV or TSV block
    headers, rows = parse_csv_or_tsv_block(text)
    if headers and rows:
        return headers, rows

    # 5. Check if user_input has explicit columns: e.g. "3 columns: Department, Employee Count, and Budget in Lakhs"
    prompt_headers = []
    if user_input:
        col_match = re.search(r"(?:columns?|headers?):\s*([^\n\.]+)", user_input, re.IGNORECASE)
        if col_match:
            raw_cols = col_match.group(1)
            prompt_headers = [clean_cell_str(c) for c in re.split(r",|\band\b", raw_cols) if clean_cell_str(c)]

    # 6. Fallback for free-form text: clean structured list without any Markdown delimiters
    lines = [clean_cell_str(line) for line in text.splitlines() if line.strip()]
    lines = [l for l in lines if not re.match(r"^[-=~#*|]+$", l) and not l.startswith("```")]
    # Skip introductory conversational phrases
    lines = [l for l in lines if not re.match(r"^(to create|i will|here is|certainly|please find|this spreadsheet)", l, re.IGNORECASE)]

    if prompt_headers and len(prompt_headers) >= 2:
        headers = prompt_headers
    else:
        headers = ["Item", "Details"]

    rows = []
    for idx, line in enumerate(lines[:50], start=1):
        if ":" in line:
            parts = line.split(":", 1)
            rows.append([clean_cell_str(parts[0]), coerce_value(parts[1])])
        else:
            rows.append([f"Item {idx}", coerce_value(line)])

    return headers, rows if rows else [["Item 1", "Completed"]]
