import re
from typing import Optional, Dict, Any

# Keywords indicating explicit spreadsheet creation or modification tasks
EXCEL_CREATION_MODIFICATION_PATTERNS = [
    r"\b(?:create|generate|build|make)\s+(?:an?\s+)?(?:excel|spreadsheet|workbook|\.xlsx)\b",
    r"\b(?:export|save)\s+(?:as|to)\s+(?:excel|spreadsheet|workbook|\.xlsx)\b",
    r"\b(?:modify|update|clean|format)\s+(?:this\s+)?(?:excel|spreadsheet|workbook|\.xlsx)\b",
    r"\b(?:remove|delete)\s+duplicates?\s+(?:in|from)\s+(?:the\s+)?(?:excel|spreadsheet|workbook|sheet)\b",
    r"\b(?:add|insert)\s+formula\s+in\s+(?:excel|spreadsheet|workbook|sheet)\b",
]

# Keywords indicating active spreadsheet data operations (when an XLSX file is present)
EXCEL_DATA_OPERATION_PATTERNS = [
    r"\banalyze\b",
    r"\binspect\b",
    r"\bsummarize\b",
    r"\bwhich\s+(?:department|column|row|item|category)\b",
    r"\b(?:highest|lowest|maximum|minimum|max|min|total|sum|average|mean|count)\b",
    r"\b(?:expenditure|spending|cost|budget|sales|revenue|amount)\b",
    r"\bfilter\s+rows?\b",
    r"\bduplicate\s+rows?\b",
    r"\bmissing\s+values?\b",
    r"\bread\s+(?:sheet|range|cells?)\b",
    r"\bhow\s+many\s+rows?\b",
]

# Conceptual patterns that should NOT trigger excel_agent even if word 'excel' appears
CONCEPTUAL_PATTERNS = [
    r"^(?:what\s+(?:is|are)|define|how\s+(?:does|to|do)|explain|give\s+me\s+a\s+(?:general\s+)?explanation(?:\s+of)?)\s+(?:what\s+(?:is|are|an?)\s+)?(?:an?\s+)?(?:excel|spreadsheet|workbook|formula|vba|macro)\b",
    r"^(?:tell\s+me\s+about|what\s+are)\s+(?:an?\s+)?(?:excel|spreadsheets?|workbooks?)\b",
    r"\b(?:general\s+explanation|concept\s+of|tutorial|overview\s+of)\s+(?:what\s+an?\s+)?(?:excel|spreadsheet|workbook)\b",
]


class TaskRouter:
    """
    Deterministic Task Router.
    Routes queries to 'excel_agent' when the task is an actual Excel operation.
    Keeps conceptual questions and ordinary text questions with general_agent/document_agent.
    """

    @classmethod
    def should_route_to_excel_agent(
        cls,
        message: str,
        active_file_type: Optional[str] = None,
        active_file_name: Optional[str] = None,
        has_xlsx_context: bool = False
    ) -> bool:
        text = message.strip().lower()
        if not text:
            return False

        # 1. If it's a purely conceptual or general knowledge question, stay on general_agent
        if any(re.search(pat, text, re.IGNORECASE) for pat in CONCEPTUAL_PATTERNS):
            return False

        # 2. Check for explicit workbook creation / modification intent
        has_creation_or_mod = any(
            re.search(pat, text, re.IGNORECASE) for pat in EXCEL_CREATION_MODIFICATION_PATTERNS
        )
        if has_creation_or_mod:
            return True

        # 3. Check if active context involves an XLSX file
        is_xlsx_context = (
            has_xlsx_context or
            (active_file_type and active_file_type.lower() in ("xlsx", "xlsm", "xls")) or
            (active_file_name and active_file_name.lower().endswith((".xlsx", ".xlsm", ".xls")))
        )

        if is_xlsx_context:
            # When an XLSX file is present, route to excel_agent ONLY if the user is performing a data operation
            has_data_op = any(
                re.search(pat, text, re.IGNORECASE) for pat in EXCEL_DATA_OPERATION_PATTERNS
            )
            # Or if the prompt specifically references the sheet, columns, file, or data
            references_data = any(
                w in text for w in ("this file", "the file", "this sheet", "this spreadsheet", "in the table", "in the sheet")
            )
            if has_data_op or references_data:
                return True

        # 4. Explicit mention of analyzing an Excel file specifically
        explicit_excel_query = re.search(
            r"\b(?:in|from|with|for)\s+(?:this\s+)?(?:the\s+)?(?:excel|spreadsheet|workbook|\.xlsx)\b",
            text,
            re.IGNORECASE
        )
        if explicit_excel_query and any(re.search(pat, text, re.IGNORECASE) for pat in EXCEL_DATA_OPERATION_PATTERNS):
            return True

        return False

    @classmethod
    def route_agent(
        cls,
        selected_agent_id: str,
        message: str,
        active_file_type: Optional[str] = None,
        active_file_name: Optional[str] = None,
        has_xlsx_context: bool = False,
        observability_service: Optional[Any] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Determines the target agent_id for the request and emits routing telemetry.
        """
        target = selected_agent_id
        routed_reason = None

        # If user explicitly selected excel_agent, respect that choice
        if selected_agent_id == "excel_agent":
            target = "excel_agent"
            routed_reason = "explicit_user_selection"
        elif selected_agent_id in ("general_agent", "document_agent"):
            if cls.should_route_to_excel_agent(
                message=message,
                active_file_type=active_file_type,
                active_file_name=active_file_name,
                has_xlsx_context=has_xlsx_context
            ):
                target = "excel_agent"
                routed_reason = "excel_data_operation_matched"
            else:
                routed_reason = "default_agent_retained"

        if observability_service:
            try:
                import asyncio
                from app.core.observability.schemas import TelemetryEventCreate
                evt = TelemetryEventCreate(
                    event_type="router.task_routed",
                    component="router",
                    severity="INFO",
                    user_id=user_id,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    status="success",
                    metadata={
                        "selected_agent": selected_agent_id,
                        "target_agent": target,
                        "routed": (target != selected_agent_id),
                        "reason": routed_reason or "selection"
                    }
                )
                asyncio.create_task(observability_service.emit_event(evt))
            except Exception:
                pass

        return target
