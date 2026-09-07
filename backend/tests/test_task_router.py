import pytest
from app.core.runtime.task_router import TaskRouter


def test_explicit_agent_selection():
    # User chose excel_agent in the UI
    res = TaskRouter.route_agent(
        selected_agent_id="excel_agent",
        message="What is the weather?"
    )
    assert res == "excel_agent"


def test_automatic_excel_creation_modification():
    # Prompt asks to create or generate spreadsheet
    r1 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Create an Excel report containing departments and their expenditure."
    )
    assert r1 == "excel_agent"

    r2 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Modify this Excel file and remove duplicate rows."
    )
    assert r2 == "excel_agent"

    r3 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Generate a spreadsheet with server uptime data."
    )
    assert r3 == "excel_agent"


def test_active_xlsx_file_data_operations():
    # Active XLSX file present and user asks for data calculation/inspection
    r1 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Which department spent the most?",
        active_file_type="xlsx",
        active_file_name="expenses.xlsx"
    )
    assert r1 == "excel_agent"

    r2 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="What is the total expenditure in this sheet?",
        active_file_type="xlsx"
    )
    assert r2 == "excel_agent"

    r3 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Filter rows where Status is Approved",
        has_xlsx_context=True
    )
    assert r3 == "excel_agent"


def test_conceptual_questions_not_routed_to_excel():
    # Crucial user correction: conceptual questions stay on general_agent!
    c1 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Give me a general explanation of what an Excel workbook is.",
        active_file_type="xlsx"
    )
    assert c1 == "general_agent"

    c2 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="What is an Excel formula?",
        has_xlsx_context=True
    )
    assert c2 == "general_agent"

    c3 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="Explain what a spreadsheet is."
    )
    assert c3 == "general_agent"


def test_text_documents_with_incidental_words_not_routed():
    # Crucial user correction: words like 'rows' in normal questions do NOT hijack routing
    r1 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="What are the rows in this document?"
    )
    assert r1 == "general_agent"

    r2 = TaskRouter.route_agent(
        selected_agent_id="document_agent",
        message="How many columns of text are in the pump manual?"
    )
    assert r2 == "document_agent"

    r3 = TaskRouter.route_agent(
        selected_agent_id="general_agent",
        message="What is the storage capacity of SRV-DB01?"
    )
    assert r3 == "general_agent"
