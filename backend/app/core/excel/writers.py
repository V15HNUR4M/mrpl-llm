import io
import os
import re
import uuid
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from typing import Dict, Any, Optional, List
from pathlib import Path
from app.core.excel.resolver import resolve_excel_file_path
from app.services.file_export import GeneratedFileManager, sanitize_filename


def create_workbook(
    sheet_name: str = "Data",
    headers: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new, professionally formatted Excel workbook locally using openpyxl.
    - Sets header row styling (dark navy fill, white bold font, border, height)
    - Automatically calculates column widths and row heights
    - Stores numeric values as actual int/float (not strings) and aligns numbers right, text left
    - Applies freeze panes and enables Excel table auto-filters
    - Sanitizes any leftover markdown delimiters
    Returns a staging file_id that can be modified or saved.
    """
    from app.core.excel.table_parser import clean_cell_str, coerce_value

    wb = openpyxl.Workbook()
    ws = wb.active
    
    # Use clean sheet name (e.g. Data) unless explicitly specified
    clean_title = "Data" if not sheet_name or sheet_name.lower() in ("sheet1", "sheet") else sheet_name
    ws.title = str(clean_title)[:31]

    # Professional palette: Deep Navy header (#0F172A), Slate borders (#CBD5E1), Zebra striping (#F8FAFC)
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_font = Font(name="Calibri", size=10, color="1E293B")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    current_row = 1

    # Optional document title banner
    if title:
        ws.cell(row=current_row, column=1, value=clean_cell_str(title))
        title_cell = ws.cell(row=current_row, column=1)
        title_cell.font = Font(name="Calibri", size=14, bold=True, color="0F172A")
        ws.row_dimensions[current_row].height = 30
        current_row += 2

    header_row_idx = current_row

    # Clean and write Headers
    if headers:
        cleaned_headers = [clean_cell_str(str(h)) for h in headers]
        ws.row_dimensions[header_row_idx].height = 26
        for col_idx, h in enumerate(cleaned_headers, start=1):
            cell = ws.cell(row=header_row_idx, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
        
        # Freeze panes below header
        ws.freeze_panes = f"A{header_row_idx + 1}"
        current_row += 1
    else:
        cleaned_headers = []

    # Clean and write Data Rows
    cleaned_row_count = 0
    if rows:
        for r_idx, row_data in enumerate(rows):
            r_num = current_row + r_idx
            ws.row_dimensions[r_num].height = 20
            is_alt = (r_idx % 2 == 1)
            for c_idx, raw_val in enumerate(row_data, start=1):
                val = coerce_value(raw_val)
                cell = ws.cell(row=r_num, column=c_idx, value=val)
                cell.font = data_font
                cell.border = thin_border
                if is_alt:
                    cell.fill = alt_fill

                # Align numbers to right, text to left
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = "#,##0.00" if isinstance(val, float) else "#,##0"
                elif isinstance(val, bool):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
            cleaned_row_count += 1

    # Enable Excel filters on the table
    if cleaned_headers and cleaned_row_count > 0:
        last_col_letter = get_column_letter(len(cleaned_headers))
        end_row = header_row_idx + cleaned_row_count
        ws.auto_filter.ref = f"A{header_row_idx}:{last_col_letter}{end_row}"

    # Auto-fit column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    # Save to staging buffer / file
    staging_id = str(uuid.uuid4())
    manager = GeneratedFileManager()
    staging_path = manager.storage_dir / f"{staging_id}.xlsx"
    wb.save(str(staging_path))

    return {
        "staging_file_id": staging_id,
        "sheet_name": ws.title,
        "total_rows": cleaned_row_count,
        "total_columns": len(cleaned_headers),
        "status": "created"
    }


def write_cells(
    file_id: str,
    start_cell: str,
    data: List[List[Any]],
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Writes data to a grid of cells starting at `start_cell` (e.g. 'A1' or 'C5').
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    wb = openpyxl.load_workbook(str(file_path))
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        start_col_letter = re.match(r"([A-Za-z]+)", start_cell).group(1).upper()
        start_row = int(re.search(r"(\d+)", start_cell).group(1))
        start_col = openpyxl.utils.column_index_from_string(start_col_letter)

        cells_written = 0
        for r_idx, row_vals in enumerate(data):
            for c_idx, val in enumerate(row_vals):
                ws.cell(row=start_row + r_idx, column=start_col + c_idx, value=val)
                cells_written += 1

        wb.save(str(file_path))
        return {
            "file_id": file_id,
            "cells_written": cells_written,
            "status": "updated"
        }
    finally:
        wb.close()


def add_formula(
    file_id: str,
    cell: str,
    formula: str,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inserts an Excel formula into a specific cell (e.g. cell='D12', formula='=SUM(D2:D11)').
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    wb = openpyxl.load_workbook(str(file_path))
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        if not formula.startswith("="):
            formula = f"={formula}"

        target_cell = ws[cell]
        target_cell.value = formula
        target_cell.font = Font(name="Calibri", size=10, bold=True, color="0F172A")

        wb.save(str(file_path))
        return {
            "file_id": file_id,
            "cell": cell,
            "formula": formula,
            "status": "formula_added"
        }
    finally:
        wb.close()


def format_range(
    file_id: str,
    range_str: str,
    number_format: Optional[str] = None,
    bold: bool = False,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Applies formatting (number format, font bold) to a cell or range of cells.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    wb = openpyxl.load_workbook(str(file_path))
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        cells = ws[range_str]

        cell_list = []
        if isinstance(cells, tuple):
            for row in cells:
                for c in row:
                    cell_list.append(c)
        else:
            cell_list.append(cells)

        for c in cell_list:
            if number_format:
                c.number_format = number_format
            if bold:
                c.font = Font(name=c.font.name or "Calibri", size=c.font.size or 10, bold=True, color=c.font.color)

        wb.save(str(file_path))
        return {
            "file_id": file_id,
            "range": range_str,
            "cells_formatted": len(cell_list),
            "status": "formatted"
        }
    finally:
        wb.close()


async def save_workbook(
    file_id: str,
    output_filename: Optional[str] = None,
    owner_id: str = "default_user",
    conversation_id: str = "default_conversation"
) -> Dict[str, Any]:
    """
    Persists and registers the created or modified workbook in the GeneratedFileManager,
    making it ready for secure download.
    """
    file_path = resolve_excel_file_path(file_id, owner_id=None)
    content_bytes = file_path.read_bytes()

    fname = output_filename or file_path.name
    if not fname.endswith(".xlsx"):
        fname = f"{fname}.xlsx"

    manager = GeneratedFileManager()
    file_record = await manager.save_file(
        owner_id=owner_id,
        conversation_id=conversation_id,
        filename=fname,
        content_bytes=content_bytes,
        file_type="xlsx"
    )

    return file_record
