import re
from typing import Dict, Any, Optional, List
from app.core.runtime.tool_executor import Tool, AuthorizationPolicy
from app.core.runtime.schemas import ToolResult
from app.core.excel.readers import read_workbook, inspect_sheet, read_range
from app.core.excel.analysis import aggregate_data, filter_rows, detect_duplicates, detect_missing_values
from app.core.excel.writers import create_workbook, write_cells, add_formula, format_range, save_workbook


class ReadWorkbookTool(Tool):
    @property
    def name(self) -> str:
        return "read_workbook"

    @property
    def description(self) -> str:
        return "Inspect an Excel workbook to list sheet names, active sheet, and sheet dimensions."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file to read."}
            },
            "required": ["file_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = read_workbook(arguments["file_id"], owner_id=user_id)
        return ToolResult(output=result, status="success")


class InspectSheetTool(Tool):
    @property
    def name(self) -> str:
        return "inspect_sheet"

    @property
    def description(self) -> str:
        return "Inspect schema, column types, row counts, null values, duplicates, and sample records of an Excel sheet."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "sheet_name": {"type": "string", "description": "Optional sheet name (defaults to active sheet)."}
            },
            "required": ["file_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = inspect_sheet(arguments["file_id"], sheet_name=arguments.get("sheet_name"), owner_id=user_id)
        return ToolResult(output=result, status="success")


class ReadRangeTool(Tool):
    @property
    def name(self) -> str:
        return "read_range"

    @property
    def description(self) -> str:
        return "Read a bounded range of cells (e.g. A1:E20) from an Excel worksheet."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "range_str": {"type": "string", "description": "Cell range such as 'A1:D15'."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "range_str"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = read_range(arguments["file_id"], arguments["range_str"], sheet_name=arguments.get("sheet_name"), owner_id=user_id)
        return ToolResult(output=result, status="success")


class AggregateDataTool(Tool):
    @property
    def name(self) -> str:
        return "aggregate_data"

    @property
    def description(self) -> str:
        return "Deterministically calculate sums, averages, counts, min/max, or group-by aggregations on spreadsheet columns using Python."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "agg_column": {"type": "string", "description": "Column name to calculate aggregates for."},
                "group_by": {"type": "string", "description": "Optional column name to group by (e.g. 'Department')."},
                "operation": {"type": "string", "description": "Operation: 'sum', 'mean', 'count', 'min', 'max'."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "agg_column"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = aggregate_data(
            file_id=arguments["file_id"],
            agg_column=arguments["agg_column"],
            group_by=arguments.get("group_by"),
            operation=arguments.get("operation", "sum"),
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class FilterRowsTool(Tool):
    @property
    def name(self) -> str:
        return "filter_rows"

    @property
    def description(self) -> str:
        return "Filter rows in an Excel sheet matching conditional criteria (==, !=, >, >=, <, <=, contains)."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "column": {"type": "string", "description": "Column name to evaluate."},
                "operator": {"type": "string", "description": "Comparison operator (==, !=, >, <, contains)."},
                "value": {"description": "Value to match or compare against."},
                "limit": {"type": "integer", "description": "Max rows to return (default 50)."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "column", "operator", "value"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = filter_rows(
            file_id=arguments["file_id"],
            column=arguments["column"],
            operator=arguments["operator"],
            value=arguments["value"],
            limit=arguments.get("limit", 50),
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class DetectDuplicatesTool(Tool):
    @property
    def name(self) -> str:
        return "detect_duplicates"

    @property
    def description(self) -> str:
        return "Detect duplicate rows across an Excel worksheet or specific key columns."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "subset": {"type": "array", "items": {"type": "string"}, "description": "Optional subset of columns."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = detect_duplicates(
            file_id=arguments["file_id"],
            subset=arguments.get("subset"),
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class DetectMissingValuesTool(Tool):
    @property
    def name(self) -> str:
        return "detect_missing_values"

    @property
    def description(self) -> str:
        return "Detect missing, null, or empty cells per column in an Excel sheet."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The UUID of the Excel file."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = detect_missing_values(
            file_id=arguments["file_id"],
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class CreateWorkbookTool(Tool):
    @property
    def name(self) -> str:
        return "create_workbook"

    @property
    def description(self) -> str:
        return "Create a new styled Excel workbook (.xlsx) with headers, data rows, freeze panes, and auto-filters."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string", "description": "Name for the worksheet."},
                "headers": {"type": "array", "items": {"type": "string"}, "description": "List of header strings."},
                "rows": {"type": "array", "items": {"type": "array"}, "description": "2D array of row data."},
                "title": {"type": "string", "description": "Optional report title banner."},
                "output_filename": {"type": "string", "description": "Optional filename for user download e.g. 'department-budget.xlsx'."}
            },
            "required": ["headers", "rows"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        result = create_workbook(
            sheet_name=arguments.get("sheet_name", "Data"),
            headers=arguments.get("headers"),
            rows=arguments.get("rows"),
            title=arguments.get("title")
        )
        
        user_id = context.get("user_id", "default_user")
        conversation_id = context.get("conversation_id", "default_conversation")
        
        output_filename = arguments.get("output_filename")
        if not output_filename:
            sheet = arguments.get("sheet_name") or "spreadsheet"
            clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '-', sheet.lower()).strip('-') or "spreadsheet"
            output_filename = f"{clean_name}.xlsx"
        if not output_filename.endswith(".xlsx"):
            output_filename = f"{output_filename}.xlsx"

        saved_meta = await save_workbook(
            file_id=result["staging_file_id"],
            output_filename=output_filename,
            owner_id=user_id,
            conversation_id=conversation_id
        )

        result.update(saved_meta)
        result["file_id"] = saved_meta["file_id"]
        result["filename"] = saved_meta["filename"]
        result["file_type"] = "xlsx"
        result["download_url"] = f"/api/v1/files/download/{saved_meta['file_id']}"
        result["status"] = "created_and_saved"

        return ToolResult(output=result, status="success", metadata={"generated_file": saved_meta})


class WriteCellsTool(Tool):
    @property
    def name(self) -> str:
        return "write_cells"

    @property
    def description(self) -> str:
        return "Write values to a grid of cells in an existing Excel workbook starting from a cell reference."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the Excel file."},
                "start_cell": {"type": "string", "description": "Starting cell e.g. 'A2' or 'C5'."},
                "data": {"type": "array", "items": {"type": "array"}, "description": "2D array of cell values."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "start_cell", "data"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = write_cells(
            file_id=arguments["file_id"],
            start_cell=arguments["start_cell"],
            data=arguments["data"],
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class AddFormulaTool(Tool):
    @property
    def name(self) -> str:
        return "add_formula"

    @property
    def description(self) -> str:
        return "Add a calculation formula (e.g. =SUM(B2:B10)) to a cell in an Excel workbook."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the Excel file."},
                "cell": {"type": "string", "description": "Cell reference such as 'D15'."},
                "formula": {"type": "string", "description": "Formula string such as '=SUM(D2:D14)'."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "cell", "formula"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = add_formula(
            file_id=arguments["file_id"],
            cell=arguments["cell"],
            formula=arguments["formula"],
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class FormatRangeTool(Tool):
    @property
    def name(self) -> str:
        return "format_range"

    @property
    def description(self) -> str:
        return "Apply cell formatting (number format, bold font) to a range of cells in an Excel workbook."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the Excel file."},
                "range_str": {"type": "string", "description": "Cell range such as 'B2:B20'."},
                "number_format": {"type": "string", "description": "Excel number format e.g. '#,##0.00' or '$#,##0'."},
                "bold": {"type": "boolean", "description": "Whether to make font bold."},
                "sheet_name": {"type": "string", "description": "Optional sheet name."}
            },
            "required": ["file_id", "range_str"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id")
        result = format_range(
            file_id=arguments["file_id"],
            range_str=arguments["range_str"],
            number_format=arguments.get("number_format"),
            bold=arguments.get("bold", False),
            sheet_name=arguments.get("sheet_name"),
            owner_id=user_id
        )
        return ToolResult(output=result, status="success")


class SaveWorkbookTool(Tool):
    @property
    def name(self) -> str:
        return "save_workbook"

    @property
    def description(self) -> str:
        return "Save and register an Excel workbook for user download, returning the file download metadata."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID or staging ID of the Excel file to save."},
                "output_filename": {"type": "string", "description": "Filename for user download e.g. 'department-expenditure.xlsx'."}
            },
            "required": ["file_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        user_id = context.get("user_id", "default_user")
        conversation_id = context.get("conversation_id", "default_conversation")
        result = await save_workbook(
            file_id=arguments["file_id"],
            output_filename=arguments.get("output_filename"),
            owner_id=user_id,
            conversation_id=conversation_id
        )
        return ToolResult(output=result, status="success", metadata={"generated_file": result})
