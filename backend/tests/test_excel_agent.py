import pytest
import openpyxl
from pathlib import Path
from app.core.excel import (
    create_workbook,
    read_workbook,
    inspect_sheet,
    read_range,
    aggregate_data,
    filter_rows,
    detect_duplicates,
    detect_missing_values,
    write_cells,
    add_formula,
    format_range,
    save_workbook,
    resolve_excel_file_path,
)
from app.services.file_export import GeneratedFileManager


@pytest.fixture
def sample_expenses_workbook():
    headers = ["Department", "Expenditure", "Quarter", "Status"]
    rows = [
        ["Mechanical", 1250000, "Q1", "Approved"],
        ["Electrical", 1830000, "Q1", "Approved"],
        ["IT", 970000, "Q1", "Approved"],
        ["Mechanical", 1100000, "Q2", "Pending"],
    ]
    res = create_workbook(
        sheet_name="Expenses",
        headers=headers,
        rows=rows,
        title="Department Expenditure Summary"
    )
    return res["staging_file_id"]


def test_create_and_read_workbook(sample_expenses_workbook):
    file_id = sample_expenses_workbook
    wb_info = read_workbook(file_id)

    assert wb_info["total_sheets"] == 1
    assert "Expenses" in wb_info["sheet_names"]
    assert wb_info["active_sheet"] == "Expenses"
    
    sheet0 = wb_info["sheets"][0]
    assert sheet0["name"] == "Expenses"
    assert sheet0["max_row"] >= 4


def test_inspect_sheet(sample_expenses_workbook):
    file_id = sample_expenses_workbook
    info = inspect_sheet(file_id, sheet_name="Expenses")

    assert info["total_rows"] == 4
    assert info["total_columns"] == 4
    assert info["duplicate_rows"] == 0

    col_names = [c["name"] for c in info["columns"]]
    assert "Department" in col_names
    assert "Expenditure" in col_names
    assert len(info["sample_rows"]) == 4


def test_read_range(sample_expenses_workbook):
    file_id = sample_expenses_workbook
    # In openpyxl, title was placed at row 1, header at row 3, data at row 4
    range_data = read_range(file_id, "A1:B4", sheet_name="Expenses")

    assert range_data["range"] == "A1:B4"
    assert len(range_data["values"]) == 4


def test_deterministic_aggregate_data(sample_expenses_workbook):
    file_id = sample_expenses_workbook

    # 1. Group Aggregation
    res = aggregate_data(
        file_id=file_id,
        agg_column="Expenditure",
        group_by="Department",
        operation="sum",
        sheet_name="Expenses"
    )

    assert res["operation"] == "group_sum"
    assert res["column"] == "Expenditure"
    assert res["group_by"] == "Department"
    # Mechanical: 1250000 + 1100000 = 2350000
    assert res["result"]["Mechanical"] == 2350000.0
    assert res["result"]["Electrical"] == 1830000.0
    assert res["result"]["IT"] == 970000.0

    # Deterministic Max & Min verification
    assert res["max"]["Department"] == "Mechanical"
    assert res["max"]["value"] == 2350000.0
    assert res["min"]["Department"] == "IT"
    assert res["min"]["value"] == 970000.0
    assert res["total"] == 5150000.0

    # 2. Scalar Aggregation
    scalar_res = aggregate_data(
        file_id=file_id,
        agg_column="Expenditure",
        operation="sum",
        sheet_name="Expenses"
    )
    assert scalar_res["total"] == 5150000.0
    assert scalar_res["count"] == 4
    assert scalar_res["min"] == 970000.0
    assert scalar_res["max"] == 1830000.0


def test_filter_rows(sample_expenses_workbook):
    file_id = sample_expenses_workbook

    filtered = filter_rows(
        file_id=file_id,
        column="Expenditure",
        operator=">",
        value=1200000,
        sheet_name="Expenses"
    )
    assert filtered["total_matched"] == 2  # Mechanical (1250000) and Electrical (1830000)

    dept_filtered = filter_rows(
        file_id=file_id,
        column="Department",
        operator="==",
        value="IT",
        sheet_name="Expenses"
    )
    assert dept_filtered["total_matched"] == 1


def test_detect_duplicates_and_missing_values(sample_expenses_workbook):
    file_id = sample_expenses_workbook

    dups = detect_duplicates(file_id, sheet_name="Expenses")
    assert dups["duplicate_count"] == 0

    missing = detect_missing_values(file_id, sheet_name="Expenses")
    assert missing["total_missing_cells"] == 0


def test_write_cells_and_formula(sample_expenses_workbook):
    file_id = sample_expenses_workbook

    # Update cell
    w_res = write_cells(file_id, "E4", [["Flagged"]], sheet_name="Expenses")
    assert w_res["status"] == "updated"

    # Add formula
    f_res = add_formula(file_id, "B8", "=SUM(B4:B7)", sheet_name="Expenses")
    assert f_res["status"] == "formula_added"

    # Format range
    fmt_res = format_range(file_id, "B4:B8", number_format="#,##0.00", bold=True, sheet_name="Expenses")
    assert fmt_res["status"] == "formatted"


@pytest.mark.asyncio
async def test_save_workbook(sample_expenses_workbook):
    file_id = sample_expenses_workbook
    saved_meta = await save_workbook(
        file_id=file_id,
        output_filename="q1-q2-expenses.xlsx",
        owner_id="test-analyst",
        conversation_id="conv-456"
    )

    assert saved_meta["file_type"] == "xlsx"
    assert saved_meta["filename"] == "q1-q2-expenses.xlsx"
    assert saved_meta["owner_id"] == "test-analyst"
    assert saved_meta["mime_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Verify saved file can be resolved by file_id
    resolved = resolve_excel_file_path(saved_meta["file_id"], owner_id="test-analyst")
    assert resolved.exists()
    assert resolved.suffix == ".xlsx"


def test_resolve_excel_file_path_security():
    # Invalid UUID
    with pytest.raises(ValueError):
        resolve_excel_file_path("../../etc/passwd")

    # Non-existent file
    with pytest.raises(FileNotFoundError):
        resolve_excel_file_path("00000000-0000-0000-0000-000000000000")
