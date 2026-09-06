import uuid
from typing import Dict, Any

from app.core.runtime.tool_executor import Tool, AuthorizationPolicy
from app.core.runtime.schemas import ToolResult
from app.core.context_engine.schemas import ContextCandidate
from app.core.rag.service import RAGService
from app.core.rag.schemas import RetrievalQuery

class SearchDocumentsTool(Tool):
    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service

    @property
    def name(self) -> str:
        return "search_documents"

    @property
    def description(self) -> str:
        return "Search the knowledge base for documents matching a query."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information in the documents."
                },
                "top_k": {
                    "type": "integer",
                    "description": "The number of results to return. Default is 5.",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        query_text = arguments.get("query")
        if not query_text:
            raise ValueError("Query is required")

        top_k = arguments.get("top_k", 5)
        
        # Extract user_id from runtime context explicitly
        user_id = context.get("user_id")
        if not user_id:
            raise ValueError("Unauthorized: user_id missing in context")

        query = RetrievalQuery(
            query=query_text,
            top_k=top_k,
            owner_id=user_id
        )

        results = await self.rag_service.search_documents(query)
        
        candidates = []
        for r in results:
            candidates.append(
                ContextCandidate(
                    id=f"{r.document_id}_{r.chunk_id}",
                    type="rag",
                    content=r.content,
                    source=r.filename,
                    relevance_score=r.score,
                    metadata={
                        "filename": r.filename,
                        "page": r.page_number,
                        "section": r.section,
                        "document_id": r.document_id,
                        "chunk_id": r.chunk_id
                    }
                )
            )

        return ToolResult(
            output=f"Found {len(results)} relevant document chunks.",
            context_candidates=candidates
        )

class GetDocumentTool(Tool):
    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service

    @property
    def name(self) -> str:
        return "get_document"

    @property
    def description(self) -> str:
        return "Retrieve a specific document by its ID."

    @property
    def authorization_policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy.AUTHENTICATED

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The ID of the document to retrieve."
                }
            },
            "required": ["document_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        document_id = arguments.get("document_id")
        if not document_id:
            raise ValueError("document_id is required")
            
        user_id = context.get("user_id")
        if not user_id:
            raise ValueError("Unauthorized: user_id missing in context")
            
        results = await self.rag_service.get_document_chunks(document_id, owner_id=user_id)
        
        candidates = []
        for r in results:
            candidates.append(
                ContextCandidate(
                    id=f"{r.document_id}_{r.chunk_id}",
                    type="rag",
                    content=r.content,
                    source=r.filename,
                    metadata={
                        "filename": r.filename,
                        "page": r.page_number,
                        "section": r.section,
                        "document_id": r.document_id,
                        "chunk_id": r.chunk_id
                    }
                )
            )
            
        return ToolResult(
            output=f"Retrieved {len(results)} chunks for document {document_id}.",
            context_candidates=candidates
        )
