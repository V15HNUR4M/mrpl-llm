import openpyxl
import pandas as pd
from typing import Dict, Any, Optional, List
from pathlib import Path
from app.core.excel.resolver import resolve_excel_file_path


def read_workbook(file_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspects an Excel workbook structure:
    - Lists all worksheets
    - Identifies active worksheet
    - Extracts dimensions (rows, cols) and header row preview for each sheet.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    wb = openpyxl.load_workbook(filename=str(file_path), read_only=True, data_only=True)
    try:
        sheet_summaries = []
        for name in wb.sheetnames:
            ws = wb[name]
            headers = []
            # Read first row with values
            for row in ws.iter_rows(values_only=True, max_row=5):
                if any(cell is not None for cell in row):
                    headers = [str(c) if c is not None else "" for c in row]
                    break
            sheet_summaries.append({
                "name": name,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "headers": headers
            })

        return {
            "file_id": file_id,
            "filename": file_path.name,
            "total_sheets": len(wb.sheetnames),
            "sheet_names": wb.sheetnames,
            "active_sheet": wb.active.title if wb.active else (wb.sheetnames[0] if wb.sheetnames else None),
            "sheets": sheet_summaries
        }
    finally:
        wb.close()


def load_sheet_dataframe(file_path: Path, sheet_name: Optional[Any] = None) -> pd.DataFrame:
    """
    Loads sheet into pandas DataFrame, intelligently detecting header row
    even if the sheet begins with empty rows or a single-cell title banner.
    """
    target_sheet = sheet_name if sheet_name is not None else 0
    df_raw = pd.read_excel(str(file_path), sheet_name=target_sheet, header=None)

    if df_raw.empty:
        return pd.DataFrame()

    best_header_idx = 0
    max_non_null = 0
    for idx in range(min(10, len(df_raw))):
        row = df_raw.iloc[idx]
        non_null = row.notna().sum()
        if non_null > max_non_null:
            max_non_null = non_null
            best_header_idx = idx

    header_row = [str(c).strip() if pd.notna(c) else f"Column_{i}" for i, c in enumerate(df_raw.iloc[best_header_idx])]
    data_df = df_raw.iloc[best_header_idx + 1:].reset_index(drop=True)
    data_df.columns = header_row
    data_df = data_df.dropna(how='all').reset_index(drop=True)
    return data_df


def inspect_sheet(file_id: str, sheet_name: Optional[str] = None, owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs in-depth inspection of a specific worksheet schema and quality:
    - Column names and data types
    - Total row and column counts
    - Missing value count per column
    - Duplicate row count
    - First 5 sample rows
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    df = load_sheet_dataframe(file_path, sheet_name=sheet_name)

    total_rows = len(df)
    total_cols = len(df.columns)
    duplicate_rows = int(df.duplicated().sum())

    columns_info = []
    for col in df.columns:
        col_series = df[col]
        null_count = int(col_series.isna().sum())
        dtype_str = str(col_series.dtype)
        columns_info.append({
            "name": str(col),
            "type": dtype_str,
            "non_null_count": int(col_series.count()),
            "null_count": null_count,
            "unique_values": int(col_series.nunique(dropna=True))
        })

    # Sample rows (head 5) sanitized for JSON
    sample_df = df.head(5).fillna("")
    # Convert timestamps/dates to string
    sample_records = []
    for record in sample_df.to_dict(orient="records"):
        sanitized_record = {}
        for k, v in record.items():
            if hasattr(v, "isoformat"):
                sanitized_record[str(k)] = v.isoformat()
            else:
                sanitized_record[str(k)] = v
        sample_records.append(sanitized_record)

    return {
        "file_id": file_id,
        "sheet_name": str(sheet_name) if sheet_name else "default",
        "total_rows": total_rows,
        "total_columns": total_cols,
        "duplicate_rows": duplicate_rows,
        "columns": columns_info,
        "sample_rows": sample_records
    }


def read_range(
    file_id: str,
    range_str: str,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reads a bounded range of cells (e.g. 'A1:E20') safely without memory overload.
    Max 1000 cells per query to prevent context exhaustion.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    wb = openpyxl.load_workbook(filename=str(file_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

        try:
            cell_range = ws[range_str]
        except Exception as e:
            raise ValueError(f"Invalid range specification '{range_str}': {str(e)}")

        # Flatten or rows
        values = []
        cell_count = 0
        
        # cell_range might be a single cell or tuple of tuples
        if isinstance(cell_range, tuple):
            for row in cell_range:
                row_vals = []
                for cell in row:
                    cell_count += 1
                    if cell_count > 1000:
                        raise ValueError("Requested range exceeds maximum safe limit of 1000 cells.")
                    val = cell.value
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    row_vals.append(val)
                values.append(row_vals)
        else:
            val = cell_range.value
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            values.append([val])

        return {
            "file_id": file_id,
            "range": range_str,
            "sheet_name": ws.title,
            "cell_count": cell_count or 1,
            "values": values
        }
    finally:
        wb.close()
