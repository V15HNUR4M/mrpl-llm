# MRPL Sovereign On-Premise Agentic AI Workbench

# API Design

## 1. Purpose

This document defines the API architecture and interface contracts for the MRPL Sovereign On-Premise Agentic AI Workbench.

The API layer provides the controlled interface between:

* React frontend
* Authentication and authorization
* Conversations
* Agent Runtime
* Context Engine
* Memory
* RAG
* Documents
* Tool Registry
* MCP
* Workflow engine
* Model Gateway
* Audit subsystem
* Administrative functions

The backend API must be implemented using **FastAPI**.

The API must not expose internal implementation details such as:

* Ollama internals
* vLLM internals
* vector database APIs
* SQLite queries
* agent implementation classes
* internal tool execution mechanisms

The API represents the platform's application contract.

---

# 2. API Architecture

```text
                         React Frontend
                               |
                               v
                         API Gateway
                               |
                         FastAPI Backend
                               |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
 Authentication          Application API       WebSocket/SSE
        |                      |
        +----------------------+----------------------+
                               |
                         Agent Runtime
                               |
        +----------+-----------+-----------+-----------+
        |          |                       |           |
        v          v                       v           v
     Memory      RAG                    Tools      Workflow
        |          |                       |           |
        +----------+-----------+-----------+-----------+
                               |
                         Model Gateway
                               |
                               v
                         Local Model
```

---

# 3. API Design Principles

The API must follow these principles:

1. REST for resource management.
2. Streaming APIs for long-running model responses.
3. Authentication on protected endpoints.
4. Authorization at service boundaries.
5. Strict request validation.
6. Structured responses.
7. Consistent error handling.
8. API versioning.
9. No direct database exposure.
10. No direct model-provider exposure.
11. No unrestricted tool execution.
12. No frontend-only security.
13. Traceable execution IDs.
14. Idempotency where side effects exist.
15. Local-first operation.
16. Provider independence.
17. Explicit API contracts.
18. Backward-compatible evolution where practical.

---

# 4. API Versioning

All public APIs should use an explicit version.

Recommended:

```text
/api/v1
```

Example:

```text
/api/v1/conversations
/api/v1/documents
/api/v1/agents
/api/v1/tools
```

Future:

```text
/api/v2
```

A breaking API change should not silently modify `/api/v1`.

---

# 5. Base URL

Development example:

```text
http://localhost:8000
```

API:

```text
http://localhost:8000/api/v1
```

Production deployment must make the host and port configurable.

---

# 6. Authentication

Protected endpoints require authentication.

Recommended initial mechanism:

```text
JWT access token
```

Flow:

```text
User
 |
 v
POST /auth/login
 |
 v
Access Token
 |
 v
Authorization: Bearer <token>
 |
 v
Protected API
```

The backend must validate the token.

The frontend must never be trusted to identify the user.

---

# 7. Authentication Endpoints

## POST `/api/v1/auth/login`

Authenticates a user.

Request:

```json
{
  "username": "operator",
  "password": "********"
}
```

Response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Invalid credentials:

```text
401 Unauthorized
```

---

# 8. Current User

## GET `/api/v1/auth/me`

Returns authenticated-user information.

Response:

```json
{
  "id": "uuid",
  "username": "operator",
  "display_name": "Operator",
  "role": "USER"
}
```

Never return:

* password hash
* access tokens
* secrets
* internal authentication state

---

# 9. Logout

## POST `/api/v1/auth/logout`

The endpoint may invalidate the session/token according to the selected authentication strategy.

For stateless JWTs, logout may be implemented through:

* short token expiration
* token revocation list
* session tracking
* refresh-token invalidation

The exact implementation should remain configurable.

---

# 10. Health Endpoints

## GET `/health`

Returns basic service availability.

Example:

```json
{
  "status": "ok"
}
```

This endpoint should not require authentication for container orchestration health checks unless deployment requirements dictate otherwise.

---

# 11. Detailed Health

## GET `/api/v1/system/health`

Returns dependency status.

Example:

```json
{
  "status": "healthy",
  "services": {
    "database": "healthy",
    "model_gateway": "healthy",
    "vector_store": "healthy",
    "workflow_engine": "healthy"
  }
}
```

Possible statuses:

```text
healthy
degraded
unavailable
unknown
```

Do not expose secrets or internal credentials.

---

# 12. Conversation APIs

## POST `/api/v1/conversations`

Creates a conversation.

Request:

```json
{
  "title": "Pump Inspection Analysis"
}
```

Response:

```json
{
  "id": "uuid",
  "title": "Pump Inspection Analysis",
  "status": "ACTIVE",
  "created_at": "2026-09-05T16:30:00Z"
}
```

The authenticated user becomes the owner.

---

# 13. List Conversations

## GET `/api/v1/conversations`

Returns conversations accessible to the authenticated user.

Query parameters:

```text
limit
offset
status
```

Example:

```text
/api/v1/conversations?limit=20&offset=0
```

The API must not return conversations belonging to unauthorized users.

---

# 14. Get Conversation

## GET `/api/v1/conversations/{conversation_id}`

Returns conversation metadata.

Authorization must be performed before returning data.

---

# 15. Delete/Archive Conversation

Recommended:

```text
POST /api/v1/conversations/{conversation_id}/archive
```

rather than immediately hard-deleting the record.

Response:

```json
{
  "id": "uuid",
  "status": "ARCHIVED"
}
```

Hard deletion should be separately controlled if required.

---

# 16. Conversation Messages

## GET `/api/v1/conversations/{conversation_id}/messages`

Returns persisted conversation messages.

Query parameters:

```text
limit
before
after
```

Example:

```text
/api/v1/conversations/{id}/messages?limit=50
```

The API should support pagination for large conversations.

---

# 17. Send Chat Message

The primary conversational API:

```text
POST /api/v1/conversations/{conversation_id}/messages
```

Request:

```json
{
  "content": "What issue was observed near the mechanical seal?",
  "agent": "auto",
  "stream": true
}
```

Possible fields:

```text
content
agent
stream
attachments
metadata
```

The frontend should normally use streaming for interactive generation.

---

# 18. Non-Streaming Chat

If:

```json
{
  "stream": false
}
```

the endpoint may return a completed response.

Example:

```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "agent": "document_agent",
  "content": "Minor leakage was observed near the mechanical seal.",
  "sources": [],
  "execution_id": "uuid"
}
```

---

# 19. Streaming Chat

For streaming:

```text
POST /api/v1/conversations/{id}/messages
```

with:

```json
{
  "content": "...",
  "stream": true
}
```

The implementation may use:

```text
Server-Sent Events (SSE)
```

or:

```text
WebSocket
```

SSE is recommended for simple server-to-client generation streaming.

WebSocket is useful when bidirectional execution events are required.

---

# 20. SSE Event Model

Example:

```text
event: execution_started
data: {...}

event: agent_selected
data: {...}

event: retrieval_started
data: {...}

event: token
data: {"text":"According"}

event: token
data: {"text":" to"}

event: source
data: {...}

event: execution_completed
data: {...}
```

The frontend should not need to understand internal Python objects.

---

# 21. Streaming Event Types

Recommended:

```text
execution_started
agent_selected
context_built
retrieval_started
retrieval_completed
tool_started
tool_completed
token
source
warning
error
execution_completed
```

Not every event needs to be displayed to the user.

---

# 22. WebSocket Endpoint

Optional endpoint:

```text
/ws/v1/conversations/{conversation_id}
```

WebSocket can support:

* token streaming
* agent status
* tool execution status
* workflow status
* cancellation
* real-time execution events

The initial implementation may use SSE first and add WebSocket where justified.

---

# 23. Message Attachments

Chat requests may contain attachments.

Example:

```json
{
  "content": "Analyze this inspection image.",
  "attachments": [
    {
      "id": "uuid",
      "type": "image"
    }
  ]
}
```

Files should not be embedded directly into normal JSON requests when unnecessary.

Use multipart upload or a separate attachment API.

---

# 24. Document APIs

## POST `/api/v1/documents`

Uploads a document.

Supported initial formats:

```text
PDF
TXT
DOCX
XLSX
CSV
PPTX
```

Recommended:

```text
multipart/form-data
```

The API validates:

* file type
* file size
* extension
* MIME type
* checksum
* access policy

---

# 25. Document Upload Response

Example:

```json
{
  "document_id": "uuid",
  "version_id": "uuid",
  "filename": "inspection_report.pdf",
  "status": "PROCESSING",
  "checksum": "sha256..."
}
```

The API should return quickly.

Parsing and embedding should not block the HTTP request unnecessarily.

---

# 26. Document Processing Status

## GET `/api/v1/documents/{document_id}`

Response:

```json
{
  "id": "uuid",
  "filename": "inspection_report.pdf",
  "status": "INDEXED",
  "current_version": 2,
  "created_at": "...",
  "updated_at": "..."
}
```

---

# 27. List Documents

## GET `/api/v1/documents`

Query parameters:

```text
limit
offset
status
department
project
file_type
```

Authorization filtering must occur before results are returned.

---

# 28. Document Versions

## GET `/api/v1/documents/{document_id}/versions`

Returns available document versions.

Example:

```json
{
  "versions": [
    {
      "version_id": "uuid",
      "version_number": 2,
      "is_current": true,
      "created_at": "..."
    }
  ]
}
```

---

# 29. Document Download

## GET `/api/v1/documents/{document_id}/download`

The API must:

1. Authenticate user.
2. Authorize document access.
3. Resolve current/selected version.
4. Stream the file.

The API must not expose internal filesystem paths.

---

# 30. Document Search

## POST `/api/v1/documents/search`

Request:

```json
{
  "query": "mechanical seal leakage",
  "top_k": 5,
  "filters": {
    "department": "maintenance"
  }
}
```

Response:

```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "filename": "inspection_report.pdf",
      "page": 12,
      "section": "Seal Condition",
      "content": "Minor leakage was observed...",
      "score": 0.91
    }
  ]
}
```

The search endpoint must enforce permissions.

---

# 31. RAG Query API

The frontend normally does not need to directly invoke RAG during normal chat.

However, an explicit endpoint is useful for:

* debugging
* evaluation
* administration
* retrieval inspection

Recommended:

```text
POST /api/v1/rag/search
```

The endpoint must return source metadata.

---

# 32. Memory APIs

## GET `/api/v1/memory`

Returns authorized semantic memories.

Query:

```text
type
status
limit
```

---

# 33. Search Memory

## POST `/api/v1/memory/search`

Request:

```json
{
  "query": "pump inspection project",
  "top_k": 5
}
```

Response:

```json
{
  "results": [
    {
      "id": "uuid",
      "type": "PROJECT_CONTEXT",
      "content": "...",
      "confidence": 0.89,
      "importance": 0.74
    }
  ]
}
```

The API must not expose another user's memory.

---

# 34. Create Memory

## POST `/api/v1/memory`

Request:

```json
{
  "content": "The user is investigating pump inspection reports.",
  "type": "PROJECT_CONTEXT"
}
```

The backend should validate whether the caller is allowed to create persistent memory.

---

# 35. Update Memory

## PATCH `/api/v1/memory/{memory_id}`

Supported changes may include:

```text
content
importance
status
metadata
```

The API must preserve lifecycle rules.

---

# 36. Delete Memory

## DELETE `/api/v1/memory/{memory_id}`

Deletion must respect retention and authorization policies.

Where appropriate, mark:

```text
status = DELETED
```

rather than immediately destroying historical records.

---

# 37. Agent APIs

## GET `/api/v1/agents`

Returns available agents.

Example:

```json
{
  "agents": [
    {
      "id": "supervisor",
      "name": "Supervisor",
      "enabled": true
    },
    {
      "id": "document_agent",
      "name": "Document Agent",
      "enabled": true
    }
  ]
}
```

Do not expose internal prompts.

---

# 38. Agent Details

## GET `/api/v1/agents/{agent_id}`

Returns safe metadata:

```json
{
  "id": "document_agent",
  "name": "Document Agent",
  "description": "Answers questions using authorized documents.",
  "capabilities": [
    "rag",
    "citations"
  ]
}
```

Do not return:

* system prompts
* secrets
* internal implementation
* hidden security rules

---

# 39. Explicit Agent Execution

Optional endpoint:

```text
POST /api/v1/agents/{agent_id}/execute
```

Request:

```json
{
  "task": "Analyze the uploaded inspection report.",
  "conversation_id": "uuid"
}
```

The backend must still enforce permissions and tool restrictions.

---

# 40. Execution APIs

## GET `/api/v1/executions/{execution_id}`

Returns execution status.

Example:

```json
{
  "id": "uuid",
  "agent_id": "document_agent",
  "status": "COMPLETED",
  "started_at": "...",
  "completed_at": "..."
}
```

---

# 41. Execution Events

## GET `/api/v1/executions/{execution_id}/events`

Returns authorized execution events.

This is useful for:

* debugging
* frontend progress display
* audit investigation
* evaluation

Sensitive internal information must be filtered.

---

# 42. Cancel Execution

## POST `/api/v1/executions/{execution_id}/cancel`

The backend should attempt graceful cancellation.

Cancellation is not guaranteed if a provider/tool cannot be interrupted.

Response:

```json
{
  "execution_id": "uuid",
  "status": "CANCELLED"
}
```

---

# 43. Tool APIs

Tool APIs should primarily support administrative and observability use cases.

Agents should access tools through the Tool Registry rather than arbitrary HTTP calls.

## GET `/api/v1/tools`

Returns tools available to the authenticated user/agent.

Example:

```json
{
  "tools": [
    {
      "name": "search_documents",
      "description": "Search authorized documents",
      "enabled": true
    }
  ]
}
```

---

# 44. Tool Execution

Direct tool execution endpoint:

```text
POST /api/v1/tools/{tool_name}/execute
```

should be restricted.

The backend must perform:

```text
Authentication
    |
Authorization
    |
Schema Validation
    |
Tool Policy
    |
Approval
    |
Execution
    |
Audit
```

A normal user must not be able to execute arbitrary tools simply by knowing their names.

---

# 45. MCP APIs

MCP should remain behind the Tool Registry.

Optional administration endpoints:

```text
GET /api/v1/mcp/servers
POST /api/v1/mcp/servers
PATCH /api/v1/mcp/servers/{id}
POST /api/v1/mcp/servers/{id}/enable
POST /api/v1/mcp/servers/{id}/disable
```

MCP servers must be explicitly trusted/allowlisted.

---

# 46. Workflow APIs

n8n is the workflow execution layer.

## GET `/api/v1/workflows`

Returns workflows available to the user.

---

# 47. Start Workflow

## POST `/api/v1/workflows/{workflow_id}/execute`

Request:

```json
{
  "input": {
    "document_id": "uuid"
  }
}
```

The backend must validate:

* workflow allowlist
* user permissions
* input schema
* side-effect policy

---

# 48. Workflow Status

## GET `/api/v1/workflows/executions/{execution_id}`

Response:

```json
{
  "id": "uuid",
  "workflow_id": "report-generation",
  "status": "RUNNING",
  "started_at": "..."
}
```

---

# 49. Model APIs

The frontend may need safe model metadata.

## GET `/api/v1/models`

Response:

```json
{
  "models": [
    {
      "id": "qwen-local",
      "provider": "ollama",
      "enabled": true,
      "context_window": 32768,
      "supports_vision": true,
      "supports_tools": true
    }
  ]
}
```

Do not expose:

* provider credentials
* internal network secrets
* raw configuration files

---

# 50. Model Selection

Users may optionally select a model if permitted.

Example:

```json
{
  "content": "Summarize this document.",
  "model": "qwen-local"
}
```

The backend must validate:

```text
Does model exist?
Is model enabled?
Can this user access it?
Does it support required capabilities?
```

The client cannot force an unavailable model.

---

# 51. System Configuration APIs

Administrative endpoints:

```text
GET /api/v1/admin/config
PATCH /api/v1/admin/config
```

These must be restricted to authorized administrators.

Sensitive configuration must be masked.

Example:

```json
{
  "default_model": "qwen-local",
  "rag_enabled": true,
  "memory_enabled": true
}
```

---

# 52. Audit APIs

## GET `/api/v1/audit/events`

Admin/auditor-only endpoint.

Query parameters:

```text
user_id
conversation_id
action
resource_type
start_time
end_time
severity
limit
offset
```

Results must respect audit access permissions.

---

# 53. Audit Event Response

Example:

```json
{
  "id": "uuid",
  "timestamp": "...",
  "action": "TOOL_EXECUTION",
  "user_id": "uuid",
  "conversation_id": "uuid",
  "resource_type": "tool",
  "resource_id": "search_documents",
  "result": "SUCCESS"
}
```

Do not expose sensitive payloads unnecessarily.

---

# 54. Error Model

All API errors should follow a consistent structure.

Recommended:

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "The requested document was not found.",
    "request_id": "uuid",
    "details": {}
  }
}
```

---

# 55. HTTP Status Codes

Recommended:

| Status | Meaning                         |
| ------ | ------------------------------- |
| 200    | Successful request              |
| 201    | Resource created                |
| 202    | Accepted for async processing   |
| 204    | Successful request without body |
| 400    | Invalid request                 |
| 401    | Authentication required/failed  |
| 403    | Authorization denied            |
| 404    | Resource not found              |
| 409    | Conflict                        |
| 413    | Payload too large               |
| 422    | Validation error                |
| 429    | Rate limit                      |
| 500    | Internal server error           |
| 502    | Dependency/provider failure     |
| 503    | Service unavailable             |
| 504    | Dependency timeout              |

---

# 56. Error Codes

Use stable application-level error codes.

Examples:

```text
AUTH_INVALID_CREDENTIALS
AUTH_TOKEN_EXPIRED
AUTH_FORBIDDEN

CONVERSATION_NOT_FOUND
MESSAGE_INVALID

DOCUMENT_NOT_FOUND
DOCUMENT_UNAUTHORIZED
DOCUMENT_PROCESSING_FAILED

RAG_UNAVAILABLE
RAG_NO_EVIDENCE

MEMORY_NOT_FOUND
MEMORY_UNAUTHORIZED

AGENT_NOT_FOUND
AGENT_EXECUTION_FAILED

TOOL_NOT_FOUND
TOOL_FORBIDDEN
TOOL_VALIDATION_FAILED
TOOL_EXECUTION_FAILED

MODEL_UNAVAILABLE
MODEL_CAPABILITY_UNSUPPORTED

CONTEXT_OVERFLOW
CONTEXT_BUILD_FAILED

WORKFLOW_NOT_FOUND
WORKFLOW_EXECUTION_FAILED
```

---

# 57. Request IDs

Every API request should have a request ID.

Example:

```text
X-Request-ID: 8b6f...
```

If the client does not provide one, the backend should generate it.

The request ID should appear in:

* logs
* errors
* audit metadata where appropriate
* execution tracing

---

# 58. Execution IDs

Long-running operations should have their own execution IDs.

Example:

```text
request_id
    |
    v
agent_execution_id
    |
    +--> tool_execution_id
    |
    +--> workflow_execution_id
```

This enables complete request tracing.

---

# 59. Idempotency

Side-effecting APIs should support idempotency where appropriate.

Example:

```text
POST /workflows/{id}/execute
Idempotency-Key: abc123
```

If the same request is retried:

```text
Same key
    |
    v
Existing execution
```

rather than starting duplicate work.

---

# 60. Pagination

List APIs should use pagination.

Recommended:

```text
limit
offset
```

Future cursor-based pagination may be introduced.

Response:

```json
{
  "items": [],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 100
  }
}
```

---

# 61. Filtering

Filtering must use explicit query parameters.

Avoid accepting arbitrary SQL-like filters from clients.

Bad:

```text
?filter=raw SQL
```

Good:

```text
?status=INDEXED&file_type=pdf
```

---

# 62. Sorting

Sorting should use allowlisted fields.

Example:

```text
?sort=updated_at&order=desc
```

The backend must reject arbitrary SQL expressions.

---

# 63. Request Validation

FastAPI/Pydantic models should validate:

* required fields
* string lengths
* enum values
* numeric ranges
* file sizes
* identifiers
* nested structures

Example:

```python
class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    stream: bool = True
```

Limits must be configurable.

---

# 64. File Upload Validation

Uploaded files must be checked using:

```text
extension
MIME type
file signature
size
checksum
```

Never trust the filename alone.

Uploads should be treated as untrusted data.

---

# 65. Rate Limiting

Rate limits should exist for:

* login
* document upload
* chat
* tool execution
* workflow execution
* administrative APIs

The exact limits should be configurable.

Example:

```yaml
rate_limits:
  login: 10/minute
  chat: 60/minute
  upload: 20/hour
```

These are example values.

---

# 66. Authorization

Every protected resource follows:

```text
Request
 |
 v
Authenticate
 |
 v
Identify User
 |
 v
Authorize Action
 |
 v
Access Resource
```

Never:

```text
Request
 |
 v
Database
 |
 v
Check ownership later
```

Authorization must happen before sensitive data is returned.

---

# 67. RBAC

API authorization should support role-based permissions.

Example:

```text
USER
    |
    +--> Chat
    +--> Own conversations
    +--> Authorized documents

OPERATOR
    |
    +--> Workflow execution
    +--> Operational tools

ADMIN
    |
    +--> Configuration
    +--> User management
    +--> Audit

AUDITOR
    |
    +--> Audit access
```

The exact permission matrix should be defined in the security implementation.

---

# 68. Agent Authorization

Agent selection does not grant permission.

For example:

```text
User
 |
 v
Supervisor
 |
 v
Tool Agent
```

The Tool Agent still operates under:

```text
User permissions
+
Agent permissions
+
Tool permissions
```

---

# 69. API and Context Engine

The API should never directly construct the final LLM prompt.

Correct:

```text
API
 |
 v
Agent Runtime
 |
 v
Context Engine
 |
 v
Model Gateway
```

Incorrect:

```text
API
 |
 v
Build giant prompt
 |
 v
Ollama
```

---

# 70. API and RAG

The API invokes the RAG service.

It does not directly access:

```text
Chroma
Qdrant
FAISS
```

The dependency direction is:

```text
API
 |
 v
RAG Service
 |
 v
Vector Store
```

---

# 71. API and Memory

Similarly:

```text
API
 |
 v
Memory Service
 |
 v
Repository / Vector Store
```

The API must not contain semantic-memory ranking logic.

---

# 72. API and Tools

```text
API
 |
 v
Tool Service
 |
 v
Tool Registry
 |
 v
Authorization
 |
 v
Execution
```

The API must not allow:

```text
POST /execute-shell
```

or equivalent unrestricted capabilities.

---

# 73. API and Model Gateway

The API should communicate with the Agent Runtime rather than directly with Ollama/vLLM.

```text
Frontend
 |
 v
FastAPI
 |
 v
Agent Runtime
 |
 v
Model Gateway
 |
 v
Local Model
```

This prevents provider-specific logic from leaking into the API layer.

---

# 74. Async Processing

The following operations should normally be asynchronous/background operations:

* document parsing
* document embedding
* vector indexing
* long-running agent execution
* report generation
* workflow execution

The API should return:

```text
202 Accepted
```

when appropriate.

---

# 75. Background Job Pattern

Example:

```text
POST /documents
      |
      v
Create Document
      |
      v
status = PROCESSING
      |
      v
202 Accepted
      |
      v
Background Worker
      |
      v
Parsing
      |
      v
Chunking
      |
      v
Embedding
      |
      v
Indexing
      |
      v
status = INDEXED
```

---

# 76. API Security Headers

The backend should use appropriate security headers where applicable.

Examples:

```text
Content-Security-Policy
X-Content-Type-Options
X-Frame-Options
Referrer-Policy
```

Exact configuration depends on deployment topology.

---

# 77. CORS

Development may allow the React development server.

Production should use a strict allowlist.

Example:

```yaml
cors:
  allowed_origins:
    - http://localhost:3000
```

Do not use unrestricted:

```text
*
```

in production unless explicitly justified.

---

# 78. API Documentation

FastAPI automatically provides OpenAPI documentation.

Development endpoints:

```text
/docs
/redoc
/openapi.json
```

Production access should be configurable.

Sensitive internal endpoints should not be unintentionally exposed.

---

# 79. OpenAPI Contract

The OpenAPI schema should document:

* request models
* response models
* authentication
* error responses
* enums
* pagination
* streaming behavior where possible

The frontend can use generated TypeScript clients later.

---

# 80. API Project Structure

Recommended:

```text
backend/
└── app/
    ├── api/
    │   ├── v1/
    │   │   ├── auth.py
    │   │   ├── conversations.py
    │   │   ├── messages.py
    │   │   ├── documents.py
    │   │   ├── rag.py
    │   │   ├── memory.py
    │   │   ├── agents.py
    │   │   ├── tools.py
    │   │   ├── workflows.py
    │   │   ├── models.py
    │   │   ├── executions.py
    │   │   ├── audit.py
    │   │   └── admin.py
    │   │
    │   ├── dependencies.py
    │   ├── middleware.py
    │   └── errors.py
    │
    ├── services/
    ├── agents/
    ├── context/
    ├── rag/
    ├── memory/
    ├── tools/
    ├── models/
    └── db/
```

---

# 81. Dependency Injection

FastAPI dependency injection should be used for:

* authenticated user
* database session
* authorization service
* service instances
* request context

Example:

```python
@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    ...
```

---

# 82. Service Boundary

API handlers should remain thin.

Bad:

```text
Endpoint
 |
 +--> SQL query
 +--> RAG query
 +--> prompt creation
 +--> model call
 +--> audit
```

Good:

```text
Endpoint
 |
 v
Application Service
 |
 +--> Authorization
 +--> Agent Runtime
 +--> Context Engine
 +--> Persistence
 +--> Audit
```

---

# 83. API Transaction Rules

Do not hold database transactions during:

* LLM generation
* document parsing
* embedding
* vector search
* external workflow execution
* long-running tools

Persist state before and after expensive operations.

---

# 84. Chat Request Flow

Complete flow:

```text
Frontend
   |
   v
POST /conversations/{id}/messages
   |
   v
Authenticate
   |
   v
Authorize Conversation
   |
   v
Persist User Message
   |
   v
Agent Runtime
   |
   v
Supervisor
   |
   v
Context Engine
   |
   +--> Memory
   +--> RAG
   +--> Tools
   |
   v
Model Gateway
   |
   v
Local Model
   |
   v
Streaming Response
   |
   v
Persist Assistant Message
   |
   v
Audit
```

---

# 85. Document Upload Flow

```text
Frontend
   |
   v
POST /documents
   |
   v
Authenticate
   |
   v
Authorize Upload
   |
   v
Validate File
   |
   v
Calculate SHA-256
   |
   v
Create Document/Version
   |
   v
202 Accepted
   |
   v
Background Ingestion
   |
   +--> Parse
   +--> Clean
   +--> Chunk
   +--> Embed
   +--> Index
   |
   v
INDEXED
```

---

# 86. Tool Execution Flow

```text
API / Agent
     |
     v
Tool Service
     |
     v
Tool Registry
     |
     v
Schema Validation
     |
     v
Authorization
     |
     v
Approval if required
     |
     v
Execute
     |
     v
Persist ToolExecution
     |
     v
Audit
```

---

# 87. Workflow Execution Flow

```text
Agent/API
   |
   v
Workflow Service
   |
   v
Allowlist
   |
   v
Authorization
   |
   v
Input Validation
   |
   v
n8n
   |
   v
Workflow
   |
   v
Execution Result
   |
   v
WorkflowExecution
   |
   v
Audit
```

---

# 88. Cancellation

Cancellation should propagate through:

```text
Frontend
 |
 v
API
 |
 v
Agent Runtime
 |
 +--> Model generation cancellation
 +--> Tool cancellation
 +--> Workflow cancellation where supported
```

Not all providers guarantee immediate cancellation.

The system should expose actual execution state rather than falsely reporting successful cancellation.

---

# 89. Timeout Policy

Different operations require different timeouts.

Example:

```yaml
timeouts:
  api_request: 30s
  model_generation: 120s
  document_processing: 600s
  tool_execution: 60s
  workflow_execution: 600s
```

Values must be configurable.

---

# 90. API Logging

Log:

* request ID
* endpoint
* method
* status
* latency
* authenticated user ID where appropriate
* execution ID

Do not log:

* passwords
* tokens
* API keys
* complete sensitive document contents
* unnecessary private conversation content

---

# 91. API Metrics

Recommended:

```text
http_requests_total
http_request_duration
http_errors_total
chat_requests_total
chat_latency
streaming_sessions
document_uploads
document_processing_duration
rag_requests
memory_requests
tool_executions
workflow_executions
authentication_failures
authorization_failures
```

---

# 92. API Testing

Tests should include:

### Authentication

* valid login
* invalid login
* expired token
* unauthorized access

### Conversations

* create
* list
* retrieve
* isolation
* archive

### Chat

* normal request
* streaming
* model unavailable
* context overflow
* RAG unavailable

### Documents

* valid upload
* invalid type
* oversized file
* unauthorized document
* duplicate document

### Tools

* unauthorized tool
* invalid schema
* successful execution
* tool failure

### Workflows

* unauthorized workflow
* invalid input
* successful execution
* workflow failure

---

# 93. API Integration Testing

At minimum test:

```text
Login
  |
Create Conversation
  |
Send Message
  |
Agent Execution
  |
RAG
  |
Model
  |
Assistant Message
  |
Audit
```

And:

```text
Upload Document
  |
Process
  |
Index
  |
Search
  |
Chat
  |
Citation
```

---

# 94. Frontend Contract

The React frontend should depend only on documented API contracts.

It must not:

* access SQLite
* access vector database
* call Ollama directly
* call vLLM directly
* execute tools directly
* enforce authorization independently

Frontend security is not sufficient.

---

# 95. API Compatibility

Avoid breaking response structures unnecessarily.

When adding fields:

```text
Existing fields remain valid.
```

When changing semantics:

```text
Introduce a new API version if necessary.
```

---

# 96. API Configuration

Example:

```yaml
api:
  host: 0.0.0.0
  port: 8000
  version: v1

cors:
  allowed_origins:
    - http://localhost:3000

limits:
  max_request_size_mb: 50

timeouts:
  request_seconds: 30
```

---

# 97. Recommended Initial Endpoint Set

The minimum useful API should include:

```text
POST   /api/v1/auth/login
GET    /api/v1/auth/me

GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/{id}
POST   /api/v1/conversations/{id}/archive
GET    /api/v1/conversations/{id}/messages
POST   /api/v1/conversations/{id}/messages

POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{id}
GET    /api/v1/documents/{id}/download
GET    /api/v1/documents/{id}/versions

POST   /api/v1/rag/search

GET    /api/v1/memory
POST   /api/v1/memory/search
POST   /api/v1/memory
PATCH  /api/v1/memory/{id}
DELETE /api/v1/memory/{id}

GET    /api/v1/agents
GET    /api/v1/agents/{id}

GET    /api/v1/executions/{id}
POST   /api/v1/executions/{id}/cancel

GET    /api/v1/tools
GET    /api/v1/workflows
POST   /api/v1/workflows/{id}/execute

GET    /api/v1/models

GET    /api/v1/system/health
```

Administrative endpoints can be added separately.

---

# 98. API Dependency Direction

The architecture must remain:

```text
React
  |
  v
API
  |
  v
Application Services
  |
  v
Agent Runtime / Domain Services
  |
  +--> Context Engine
  +--> Memory
  +--> RAG
  +--> Tool Registry
  +--> Workflow Service
  +--> Model Gateway
  |
  v
Repositories / Infrastructure
```

Never reverse this dependency.

For example:

```text
Ollama -> API business logic
```

must not occur.

---

# 99. Critical Architectural Rules

The implementation must follow these rules:

1. **All protected APIs require authentication.**

2. **Authorization must occur before sensitive resource access.**

3. **The frontend must never be the security boundary.**

4. **The API must not directly query the vector database.**

5. **The API must not directly query SQLite for business operations.**

6. **The API must not directly call Ollama or vLLM for normal agent execution.**

7. **All model execution goes through the Agent Runtime and Model Gateway.**

8. **All model context construction goes through the Context Engine.**

9. **Tool execution must pass through the Tool Registry and authorization layer.**

10. **MCP servers must remain controlled and allowlisted.**

11. **Workflow execution must pass through workflow authorization and validation.**

12. **Long-running work must not block database transactions.**

13. **Side-effecting operations should support idempotency.**

14. **Streaming must preserve execution and request identifiers.**

15. **API errors must use stable error codes.**

16. **Sensitive information must not be exposed through API errors or logs.**

17. **File uploads must be treated as untrusted input.**

18. **Pagination must be used for potentially large collections.**

19. **Arbitrary SQL/filter expressions must never be accepted from clients.**

20. **API versioning must protect existing contracts.**

21. **OpenAPI must accurately represent public contracts.**

22. **The API must remain independent of the selected open-weight model.**

23. **The API must remain independent of the selected model server.**

24. **The API must remain independent of the selected vector database.**

25. **The API must remain independent of the selected relational database.**

---

# 100. Acceptance Criteria

The API implementation is complete when:

* [ ] FastAPI application is operational.
* [ ] `/api/v1` versioning exists.
* [ ] Authentication is implemented.
* [ ] Current-user endpoint exists.
* [ ] RBAC/authorization is enforced.
* [ ] Conversation CRUD is implemented.
* [ ] Message persistence is implemented.
* [ ] Streaming chat is implemented.
* [ ] Request IDs are supported.
* [ ] Execution IDs are supported.
* [ ] Document upload is implemented.
* [ ] Document processing status is exposed.
* [ ] Document versioning is exposed.
* [ ] Authorized document download works.
* [ ] RAG search endpoint exists.
* [ ] Memory APIs exist.
* [ ] Agent metadata APIs exist.
* [ ] Agent execution status is exposed.
* [ ] Execution cancellation is supported where possible.
* [ ] Tool discovery is controlled.
* [ ] Workflow execution is controlled.
* [ ] Model metadata is exposed safely.
* [ ] Health endpoints exist.
* [ ] Consistent error responses exist.
* [ ] Pagination exists.
* [ ] Rate limiting exists or is prepared.
* [ ] CORS is configurable.
* [ ] OpenAPI documentation is generated.
* [ ] API logging avoids secrets.
* [ ] API metrics exist.
* [ ] Authentication/authorization tests exist.
* [ ] Integration tests cover end-to-end chat.
* [ ] API does not directly depend on Ollama, vLLM, Chroma, Qdrant, FAISS, or SQLite implementation details.

---

# 101. Relationship to Other Design Documents

This API design integrates with:

```text
REQUIREMENT.md
ARCHITECTURE.md
MEMORY_DESIGN.md
RAG_DESIGN.md
AGENT_DESIGN.md
SECURITY.md
EVALUATION.md
IMPLEMENTATION_PLAN.md
TOOL_MCP_DESIGN.md
CONTEXT_ENGINE_DESIGN.md
DATA_MODEL.md
```

It provides the external application interface for:

```text
Agent Runtime
Context Engine
Memory
RAG
Documents
Tools
MCP
Workflows
Model Gateway
Audit
```

The next architectural layer should define the multimodal subsystem.

---

# 102. Final Design Principle

The API must be treated as a **controlled boundary**, not as a thin HTTP wrapper around internal components.

The correct architecture is:

```text
Client
  |
  v
API
  |
  v
Authorization
  |
  v
Application Service
  |
  v
Agent Runtime
  |
  +--> Context Engine
  +--> Memory
  +--> RAG
  +--> Tools
  +--> Workflow
  |
  v
Model Gateway
  |
  v
Local Open-Weight Model
```

The API should expose **capabilities and resources**, not infrastructure internals.

That separation is what allows the MRPL Workbench to remain secure, modular, locally deployable, auditable, and replaceable as the underlying models and infrastructure evolve.
