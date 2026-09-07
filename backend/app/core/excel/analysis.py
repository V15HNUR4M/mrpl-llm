import pandas as pd
from typing import Dict, Any, Optional, List, Union
from app.core.excel.resolver import resolve_excel_file_path
from app.core.excel.readers import load_sheet_dataframe


def aggregate_data(
    file_id: str,
    agg_column: str,
    group_by: Optional[str] = None,
    operation: str = "sum",
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministically computes mathematical aggregations using pandas.
    The LLM uses these deterministic numbers directly and does not perform arithmetic.
    Operations supported: 'sum', 'mean', 'avg', 'count', 'min', 'max', 'summary'.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    df = load_sheet_dataframe(file_path, sheet_name=sheet_name)

    # Clean column names (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]
    agg_col = agg_column.strip()

    # Case-insensitive column matching
    col_map = {c.lower(): c for c in df.columns}
    if agg_col.lower() in col_map:
        agg_col = col_map[agg_col.lower()]
    else:
        raise ValueError(f"Column '{agg_column}' not found in sheet. Available columns: {list(df.columns)}")

    # Ensure numeric conversion for calculations
    df[agg_col] = pd.to_numeric(df[agg_col], errors='coerce')
    op = operation.lower().strip()

    if group_by:
        grp_col = group_by.strip()
        if grp_col.lower() in col_map:
            grp_col = col_map[grp_col.lower()]
        else:
            raise ValueError(f"Group column '{group_by}' not found. Available columns: {list(df.columns)}")

        if op in ("sum", "total"):
            grouped = df.groupby(grp_col)[agg_col].sum()
        elif op in ("mean", "avg", "average"):
            grouped = df.groupby(grp_col)[agg_col].mean()
        elif op == "count":
            grouped = df.groupby(grp_col)[agg_col].count()
        elif op == "min":
            grouped = df.groupby(grp_col)[agg_col].min()
        elif op == "max":
            grouped = df.groupby(grp_col)[agg_col].max()
        else:
            grouped = df.groupby(grp_col)[agg_col].sum()

        result_dict = {str(k): (round(float(v), 2) if pd.notna(v) else 0.0) for k, v in grouped.items()}

        # Deterministic max and min calculation
        max_item = None
        min_item = None
        if result_dict:
            max_key = max(result_dict, key=result_dict.get)
            min_key = min(result_dict, key=result_dict.get)
            max_item = {grp_col: max_key, "value": result_dict[max_key]}
            min_item = {grp_col: min_key, "value": result_dict[min_key]}

        total_sum = round(float(df[agg_col].sum(skipna=True)), 2)
        mean_val = round(float(df[agg_col].mean(skipna=True)), 2) if len(df) > 0 else 0.0

        return {
            "operation": f"group_{op}",
            "column": agg_col,
            "group_by": grp_col,
            "result": result_dict,
            "max": max_item,
            "min": min_item,
            "total": total_sum,
            "overall_mean": mean_val
        }

    # Ungrouped scalar aggregation
    total = round(float(df[agg_col].sum(skipna=True)), 2)
    mean = round(float(df[agg_col].mean(skipna=True)), 2) if len(df) > 0 else 0.0
    minimum = round(float(df[agg_col].min(skipna=True)), 2) if len(df) > 0 else 0.0
    maximum = round(float(df[agg_col].max(skipna=True)), 2) if len(df) > 0 else 0.0
    count = int(df[agg_col].count())

    return {
        "operation": f"scalar_{op}",
        "column": agg_col,
        "count": count,
        "total": total,
        "mean": mean,
        "min": minimum,
        "max": maximum
    }


def filter_rows(
    file_id: str,
    column: str,
    operator: str,
    value: Any,
    limit: int = 50,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministically filters sheet rows matching specific logical criteria.
    Supported operators: '==', '!=', '>', '>=', '<', '<=', 'contains'.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    df = load_sheet_dataframe(file_path, sheet_name=sheet_name)

    col_map = {str(c).lower().strip(): str(c) for c in df.columns}
    target_col = column.lower().strip()
    if target_col not in col_map:
        raise ValueError(f"Column '{column}' not found. Available: {list(df.columns)}")
    actual_col = col_map[target_col]

    series = df[actual_col]
    op = operator.strip()

    # Try numeric compare if value is number
    is_numeric = False
    num_val = None
    try:
        num_val = float(value)
        numeric_series = pd.to_numeric(series, errors='coerce')
        is_numeric = True
    except (ValueError, TypeError):
        pass

    if op in ("==", "="):
        mask = (numeric_series == num_val) if is_numeric else (series.astype(str).str.lower() == str(value).lower())
    elif op == "!=":
        mask = (numeric_series != num_val) if is_numeric else (series.astype(str).str.lower() != str(value).lower())
    elif op == ">":
        mask = numeric_series > num_val if is_numeric else series.astype(str) > str(value)
    elif op == ">=":
        mask = numeric_series >= num_val if is_numeric else series.astype(str) >= str(value)
    elif op == "<":
        mask = numeric_series < num_val if is_numeric else series.astype(str) < str(value)
    elif op == "<=":
        mask = numeric_series <= num_val if is_numeric else series.astype(str) <= str(value)
    elif op == "contains":
        mask = series.astype(str).str.contains(str(value), case=False, na=False)
    else:
        raise ValueError(f"Unsupported operator '{operator}'")

    filtered_df = df[mask]
    total_matched = len(filtered_df)
    sample_matched = filtered_df.head(limit).fillna("").to_dict(orient="records")

    return {
        "file_id": file_id,
        "column": actual_col,
        "operator": op,
        "filter_value": value,
        "total_matched": total_matched,
        "rows_returned": len(sample_matched),
        "matches": sample_matched
    }


def detect_duplicates(
    file_id: str,
    subset: Optional[List[str]] = None,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detects duplicate rows across the entire sheet or across specific key columns.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    df = load_sheet_dataframe(file_path, sheet_name=sheet_name)

    dup_mask = df.duplicated(subset=subset, keep=False)
    total_dups = int(dup_mask.sum())
    dup_records = df[dup_mask].head(10).fillna("").to_dict(orient="records")

    return {
        "file_id": file_id,
        "total_rows": len(df),
        "duplicate_count": total_dups,
        "duplicate_percentage": round((total_dups / len(df) * 100), 2) if len(df) > 0 else 0.0,
        "sample_duplicates": dup_records
    }


def detect_missing_values(
    file_id: str,
    sheet_name: Optional[str] = None,
    owner_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detects null, empty, and NaN cells per column in the worksheet.
    """
    file_path = resolve_excel_file_path(file_id, owner_id)
    df = load_sheet_dataframe(file_path, sheet_name=sheet_name)

    missing_cols = []
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            missing_cols.append({
                "column": str(col),
                "null_count": null_count,
                "null_percentage": round((null_count / len(df) * 100), 2) if len(df) > 0 else 0.0
            })

    return {
        "file_id": file_id,
        "total_rows": len(df),
        "columns_with_missing": missing_cols,
        "total_missing_cells": int(df.isna().sum().sum())
    }
