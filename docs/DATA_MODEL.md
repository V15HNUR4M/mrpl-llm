# MRPL Sovereign On-Premise Agentic AI Workbench

# Data Model and Persistence Design

## 1. Purpose

This document defines the persistence architecture and data model for the MRPL Sovereign On-Premise Agentic AI Workbench.

The data layer must persist the state required for:

* Users
* Authentication and authorization
* Conversations
* Messages
* Conversation summaries
* Semantic memory
* Documents
* Document versions
* Document chunks
* Agent executions
* Tool executions
* Audit events
* Workflow executions
* Model configuration
* System configuration

The initial implementation must use **SQLite** because the platform is designed to be local-first, sovereign, easy to deploy, and suitable for prototype and initial production environments.

The application must nevertheless use repository/service abstractions so SQLite can later be replaced with PostgreSQL or another relational database without rewriting business logic.

---

# 2. Persistence Philosophy

The database is the authoritative persistence layer for application state.

The LLM is never the source of truth.

The vector database is not the source of truth for documents or memories.

The following principle applies:

```text
Relational Database
        |
        +--> Authoritative metadata
        +--> Conversations
        +--> Messages
        +--> Memory metadata
        +--> Documents
        +--> Execution state
        +--> Audit
        |
        v
Vector Store
        |
        +--> Search/index representation
```

The relational database stores authoritative records.

Vector stores contain searchable representations.

---

# 3. Initial Database

Initial database:

```text
SQLite
```

Example:

```text
data/
└── mrpl.db
```

The database location must be configurable.

Example:

```yaml
database:
  engine: sqlite
  url: sqlite:///./data/mrpl.db
```

Do not hard-code the path throughout the application.

---

# 4. Database Abstraction

Business logic must not directly depend on SQLite APIs.

Recommended architecture:

```text
Service Layer
      |
      v
Repository Interfaces
      |
      v
SQLite Repository
```

Future:

```text
Service Layer
      |
      v
Repository Interfaces
      |
      +--> SQLite Repository
      +--> PostgreSQL Repository
```

---

# 5. Entity Overview

Core entities:

```text
User
Conversation
Message
ConversationSummary
Memory
Document
DocumentVersion
DocumentChunk
AgentExecution
ToolExecution
WorkflowExecution
AuditEvent
ModelConfiguration
SystemConfiguration
```

Relationship overview:

```text
User
 |
 +----< Conversation
 |          |
 |          +----< Message
 |          |
 |          +----< ConversationSummary
 |          |
 |          +----< Memory
 |          |
 |          +----< AgentExecution
 |
 +----< Memory
 |
 +----< AuditEvent

Document
 |
 +----< DocumentVersion
              |
              +----< DocumentChunk

AgentExecution
 |
 +----< ToolExecution

Conversation
 |
 +----< AgentExecution
 |
 +----< AuditEvent
```

---

# 6. ID Strategy

All major entities should use globally unique identifiers.

Recommended:

```text
UUID
```

Example:

```text
550e8400-e29b-41d4-a716-446655440000
```

The database should not depend on sequential integer IDs for externally visible entities.

UUIDs make distributed execution, imports, and future service separation easier.

---

# 7. Timestamp Strategy

All persistent entities should include appropriate timestamps.

Recommended format:

```text
UTC ISO-8601
```

Example:

```text
2026-09-05T16:30:00Z
```

Application code should use timezone-aware datetime values.

Do not rely on local machine timezone for persisted timestamps.

---

# 8. User Entity

## Purpose

Represents an authenticated platform user.

Conceptual schema:

```text
User
----
id
username
email
password_hash
display_name
role
is_active
created_at
updated_at
last_login_at
```

Recommended fields:

| Field         | Type     | Required | Description           |
| ------------- | -------- | -------: | --------------------- |
| id            | UUID     |      Yes | Unique user ID        |
| username      | TEXT     |      Yes | Login identifier      |
| email         | TEXT     |       No | Optional email        |
| password_hash | TEXT     |      Yes | Secure password hash  |
| display_name  | TEXT     |       No | Display name          |
| role          | TEXT     |      Yes | RBAC role             |
| is_active     | BOOLEAN  |      Yes | Account state         |
| created_at    | DATETIME |      Yes | Creation time         |
| updated_at    | DATETIME |      Yes | Last update           |
| last_login_at | DATETIME |       No | Last successful login |

Passwords must never be stored in plaintext.

---

# 9. User Roles

Initial roles may include:

```text
ADMIN
USER
OPERATOR
ANALYST
```

The exact RBAC design belongs to the security layer.

The database should not make role expansion difficult.

A future role such as:

```text
DOCUMENT_MANAGER
AUDITOR
WORKFLOW_OPERATOR
```

must be possible without schema redesign.

---

# 10. Conversation Entity

Represents a persistent chat session.

```text
Conversation
------------
id
user_id
title
status
created_at
updated_at
archived_at
metadata
```

Fields:

| Field       | Type      | Description             |
| ----------- | --------- | ----------------------- |
| id          | UUID      | Conversation ID         |
| user_id     | UUID      | Owner                   |
| title       | TEXT      | Conversation title      |
| status      | TEXT      | ACTIVE/ARCHIVED/DELETED |
| created_at  | DATETIME  | Creation time           |
| updated_at  | DATETIME  | Last activity           |
| archived_at | DATETIME  | Archive timestamp       |
| metadata    | JSON/TEXT | Optional metadata       |

Foreign key:

```text
conversation.user_id -> user.id
```

---

# 11. Conversation Isolation

Users must only access conversations they are authorized to access.

Every conversation query should include ownership or authorization filtering.

Incorrect:

```sql
SELECT * FROM conversations WHERE id = ?;
```

Correct conceptual behavior:

```text
conversation_id
+
authenticated_user
+
authorization policy
```

The service layer must verify ownership/permission before returning the conversation.

---

# 12. Message Entity

Stores complete conversation history.

```text
Message
-------
id
conversation_id
role
content
created_at
sequence_number
model_id
agent_id
metadata
```

Roles:

```text
user
assistant
system
tool
```

Potential additional fields:

```text
parent_message_id
token_count
status
```

---

# 13. Message Ordering

Conversation order must be deterministic.

Recommended:

```text
sequence_number
```

Example:

```text
1 USER
2 ASSISTANT
3 USER
4 ASSISTANT
```

The timestamp alone must not determine ordering.

Two messages can theoretically have the same timestamp resolution.

---

# 14. Message Persistence

Complete conversation history should be persisted.

However, complete history should not automatically be sent to the LLM.

Architecture:

```text
Complete History
      |
      v
Database
      |
      +--> Context Engine
               |
               v
        Relevant Context
```

This is a critical distinction.

---

# 15. Message Metadata

Metadata may include:

```json
{
  "model": "qwen-local",
  "agent": "document_agent",
  "execution_id": "...",
  "streaming": true
}
```

Do not store arbitrary sensitive runtime information without policy.

---

# 16. Conversation Summary Entity

Stores compressed representation of older conversation history.

```text
ConversationSummary
-------------------
id
conversation_id
summary
start_sequence
end_sequence
version
created_at
updated_at
```

Example:

```text
Conversation
Messages 1-20
      |
      v
Summary Version 1
      |
Messages 21-30
      |
      v
Summary Version 2
```

The latest valid summary can be used by the Context Engine.

---

# 17. Summary Authority

The summary is not authoritative.

Raw messages remain authoritative.

If a summary conflicts with original messages:

```text
Raw history > summary
```

The summary should be regenerated when necessary.

---

# 18. Memory Entity

Represents persistent semantic memory.

```text
Memory
------
id
user_id
conversation_id
type
content
importance
confidence
status
embedding_reference
created_at
updated_at
last_accessed_at
expires_at
metadata
```

Types:

```text
FACT
PREFERENCE
PROJECT_CONTEXT
DECISION
TASK
ENTITY
EVENT
SUMMARY
```

---

# 19. Memory Status

Recommended:

```text
ACTIVE
STALE
CONFLICTED
ARCHIVED
DELETED
```

State transitions:

```text
ACTIVE
  |
  +--> STALE
  |
  +--> CONFLICTED
  |
  +--> ARCHIVED
  |
  +--> DELETED
```

Deleted memories should follow the platform's retention policy.

---

# 20. Memory Importance

Importance should be represented numerically.

Example:

```text
0.0 - 1.0
```

Interpretation:

```text
0.9+  critical
0.7   high
0.5   medium
0.3   low
```

These thresholds should remain configurable.

---

# 21. Memory Confidence

Confidence should also be represented numerically.

The system must distinguish:

```text
importance
```

from:

```text
confidence
```

A memory can be:

```text
high importance + low confidence
```

Such a memory should not automatically be treated as authoritative.

---

# 22. Memory Embeddings

The database should not necessarily store the complete vector directly.

Instead:

```text
Memory
 |
 +--> embedding_reference
```

The actual vector may be stored in a vector store.

Example:

```text
memory.id
    |
    v
vector_store(memory_id, embedding)
```

This keeps vector infrastructure replaceable.

---

# 23. Memory Ownership

Memory may belong to:

```text
USER
CONVERSATION
PROJECT
ORGANIZATION
```

The initial implementation should prioritize:

```text
USER
CONVERSATION
```

Future project-level memory can be added through metadata or a dedicated scope entity.

---

# 24. Document Entity

Represents an uploaded knowledge document.

```text
Document
--------
id
owner_id
filename
file_type
mime_type
file_size
checksum
classification
department
project
access_scope
status
created_at
updated_at
archived_at
metadata
```

---

# 25. Document Status

Recommended:

```text
UPLOADED
PROCESSING
INDEXED
FAILED
ARCHIVED
DELETED
```

Flow:

```text
UPLOAD
  |
  v
UPLOADED
  |
  v
PROCESSING
  |
  +----> FAILED
  |
  v
INDEXED
  |
  +----> ARCHIVED
  |
  v
DELETED
```

---

# 26. Document Checksum

Each document should have a cryptographic checksum.

Recommended:

```text
SHA-256
```

Purpose:

* duplicate detection
* integrity verification
* idempotent ingestion
* version tracking

Example:

```text
checksum = SHA256(file_bytes)
```

---

# 27. Document Version

Documents may change over time.

Therefore document identity and document version should be separated.

```text
Document
   |
   +--> Version 1
   +--> Version 2
   +--> Version 3
```

Schema:

```text
DocumentVersion
---------------
id
document_id
version_number
checksum
storage_path
file_size
created_at
created_by
is_current
metadata
```

---

# 28. Version Rules

Only one version should normally be marked:

```text
is_current = true
```

for a document.

When a new version is uploaded:

```text
Old version -> is_current = false
New version -> is_current = true
```

Old versions should remain available if required for audit and traceability.

---

# 29. Document Chunk

Represents an indexed document segment.

```text
DocumentChunk
-------------
id
document_version_id
chunk_index
content
token_count
page_number
section
embedding_reference
metadata
created_at
```

Chunk content is the authoritative textual representation used by RAG.

---

# 30. Chunk Ordering

Chunks should maintain document order:

```text
chunk_index
```

Example:

```text
0
1
2
3
...
```

This allows adjacent chunks to be reconstructed when necessary.

---

# 31. Chunk Metadata

Recommended:

```text
page_number
section
heading
table_id
paragraph_id
source_offset
```

Future formats may add:

```text
sheet_name
row_range
slide_number
figure_id
```

The schema should permit extensible metadata.

---

# 32. Vector Store Relationship

The vector store should reference relational entities.

Example:

```text
DocumentChunk
id = chunk-123

Vector Store
-------------------------
chunk_id = chunk-123
embedding = [...]
```

The vector database must never become the only source of document identity.

---

# 33. Agent Execution Entity

Represents one agent-runtime execution.

```text
AgentExecution
--------------
id
conversation_id
user_id
parent_execution_id
agent_id
task_type
status
model_id
started_at
completed_at
error
metadata
```

Statuses:

```text
PENDING
RUNNING
COMPLETED
FAILED
CANCELLED
TIMED_OUT
```

---

# 34. Agent Execution Hierarchy

Agents may invoke other agents.

Example:

```text
Supervisor Execution
        |
        +--> Document Agent Execution
        |
        +--> Analysis Agent Execution
```

Therefore:

```text
parent_execution_id
```

should be supported.

This creates an execution tree.

---

# 35. Agent Execution Metadata

Metadata may include:

```json
{
  "context_policy_version": "1.0",
  "model": "qwen-local",
  "retrieval_count": 5,
  "tool_count": 2
}
```

Do not use metadata as a replacement for important relational fields.

---

# 36. Tool Execution Entity

Represents execution of a registered tool.

```text
ToolExecution
-------------
id
agent_execution_id
conversation_id
user_id
tool_name
status
input_hash
input_metadata
output_metadata
started_at
completed_at
error
approval_required
approved_by
```

Statuses:

```text
REQUESTED
VALIDATING
AUTHORIZED
EXECUTING
COMPLETED
DENIED
FAILED
CANCELLED
TIMED_OUT
```

---

# 37. Tool Input Storage

Full tool inputs should not automatically be persisted.

Sensitive tool parameters may contain:

* credentials
* internal identifiers
* personal data
* confidential information

Prefer:

```text
input_hash
+
sanitized metadata
```

Full payload persistence should be configurable.

---

# 38. Tool Output Storage

Similarly, large tool results should not necessarily be stored completely.

Recommended:

```text
result_status
result_hash
summary
metadata
```

For required audit scenarios, complete results may be stored according to retention policy.

---

# 39. Workflow Execution Entity

n8n integration requires workflow execution tracking.

```text
WorkflowExecution
-----------------
id
workflow_id
workflow_name
conversation_id
agent_execution_id
user_id
status
started_at
completed_at
external_execution_id
error
metadata
```

Statuses:

```text
REQUESTED
RUNNING
COMPLETED
FAILED
CANCELLED
TIMED_OUT
```

The local database tracks the integration.

n8n remains the workflow execution engine.

---

# 40. Audit Event Entity

Audit events are security and operational records.

```text
AuditEvent
----------
id
timestamp
user_id
conversation_id
agent_execution_id
tool_execution_id
action
resource_type
resource_id
result
severity
metadata
```

Examples:

```text
LOGIN
DOCUMENT_UPLOAD
DOCUMENT_ACCESS
MEMORY_READ
MEMORY_WRITE
RAG_QUERY
AGENT_START
AGENT_END
TOOL_REQUEST
TOOL_DENIED
TOOL_EXECUTION
WORKFLOW_START
WORKFLOW_END
CONFIG_CHANGE
```

---

# 41. Audit Immutability

Audit records should be treated as append-only.

Application code should not casually update or delete audit records.

Recommended model:

```text
Application
     |
     v
Audit Service
     |
     v
INSERT AuditEvent
```

Updates should be highly restricted.

---

# 42. Audit Traceability

An important execution should be reconstructable:

```text
User
 |
 v
Conversation
 |
 v
AgentExecution
 |
 +--> RAG retrieval metadata
 |
 +--> ToolExecution
 |
 +--> WorkflowExecution
 |
 v
Final response
```

The database should provide enough identifiers to correlate these events.

---

# 43. Model Configuration Entity

Model configuration should be persisted separately from conversation data.

Conceptual schema:

```text
ModelConfiguration
------------------
id
name
provider
model_identifier
enabled
context_window
supports_vision
supports_tools
supports_streaming
configuration
created_at
updated_at
```

Example:

```text
provider = ollama
model_identifier = qwen-local
```

The database should not assume Qwen is permanent.

---

# 44. Provider Abstraction

The model configuration should support:

```text
Ollama
vLLM
Future local provider
```

without changing the conversation schema.

---

# 45. System Configuration

Configuration that must survive application restarts may be persisted.

Examples:

```text
default_model
default_context_policy
default_embedding_model
RAG settings
retention settings
feature flags
```

Sensitive secrets should not be stored in plaintext in the database.

Prefer environment variables or secure local secret management.

---

# 46. JSON Metadata

SQLite does not need dozens of columns for every future optional attribute.

A metadata field can hold extensible information.

Example:

```json
{
  "department": "maintenance",
  "equipment_id": "P-101",
  "tags": ["pump", "inspection"]
}
```

However, metadata must not become an excuse to store everything as unstructured JSON.

Fields frequently used for:

* joins
* filtering
* authorization
* sorting
* reporting

should receive dedicated database columns.

---

# 47. Foreign Keys

SQLite foreign keys must explicitly be enabled.

Conceptually:

```sql
PRAGMA foreign_keys = ON;
```

The application must ensure this is enabled for every database connection.

---

# 48. Indexing Strategy

Important indexes include:

```text
users.username
users.email

conversations.user_id
conversations.updated_at

messages.conversation_id
messages.sequence_number

memory.user_id
memory.conversation_id
memory.status
memory.type

documents.owner_id
documents.checksum
documents.status

document_versions.document_id
document_versions.is_current

document_chunks.document_version_id
document_chunks.chunk_index

agent_executions.conversation_id
agent_executions.user_id
agent_executions.status

tool_executions.agent_execution_id
tool_executions.conversation_id
tool_executions.status

audit_events.timestamp
audit_events.user_id
audit_events.conversation_id
audit_events.action
```

---

# 49. Composite Indexes

Frequently used query combinations should receive composite indexes.

Examples:

```text
(conversation_id, sequence_number)

(user_id, updated_at)

(document_id, is_current)

(agent_execution_id, started_at)

(conversation_id, timestamp)
```

Indexes should be added based on actual query patterns.

Avoid indexing every column.

---

# 50. Database Constraints

Important constraints include:

```text
username UNIQUE
email UNIQUE where applicable
document checksum indexed/unique according to version policy
sequence_number unique per conversation
version_number unique per document
```

Foreign keys should enforce relationships.

---

# 51. Soft Deletion

For entities where audit/history matters, prefer soft deletion.

Example:

```text
status = DELETED
```

rather than immediately removing the record.

Potential candidates:

```text
Conversation
Document
Memory
```

Hard deletion may still be required for explicit data-erasure requirements.

---

# 52. Data Retention

Retention must be configurable.

Possible policies:

```yaml
retention:
  audit_days: 365
  execution_days: 90
  archived_conversations_days: 365
  deleted_documents_days: 30
```

These are example values only.

The final values must be determined by deployment requirements.

---

# 53. Transaction Boundaries

Operations involving multiple records should use transactions.

Example document ingestion:

```text
Create Document
      |
Create Version
      |
Create Chunks
      |
Commit metadata
      |
Index vectors
```

If database metadata cannot be committed:

```text
Do not mark document INDEXED
```

---

# 54. Vector Index Consistency

Database and vector store may temporarily become inconsistent.

The system should track indexing status.

Example:

```text
Document
status = PROCESSING
```

until:

```text
Database metadata
+
Chunk records
+
Vector index
```

are successfully synchronized.

Only then:

```text
status = INDEXED
```

---

# 55. Idempotent Ingestion

Repeated upload of the same document should not accidentally create uncontrolled duplicates.

Use:

```text
checksum
+
document identity
+
version policy
```

to determine whether the upload is:

* duplicate
* new version
* new document

---

# 56. Database Migration

Schema changes must use migrations.

Recommended tool:

```text
Alembic
```

for SQLAlchemy-based implementation.

Do not manually edit production database schemas.

Migration flow:

```text
Code Change
    |
    v
Migration
    |
    v
Database Upgrade
```

---

# 57. Repository Interfaces

Example:

```python
class ConversationRepository:

    async def create(self, conversation):
        ...

    async def get_by_id(self, conversation_id):
        ...

    async def list_for_user(self, user_id):
        ...

    async def update(self, conversation):
        ...

    async def archive(self, conversation_id):
        ...
```

Message repository:

```python
class MessageRepository:

    async def create(self, message):
        ...

    async def list_by_conversation(self, conversation_id):
        ...

    async def get_recent(self, conversation_id, limit):
        ...
```

---

# 58. Memory Repository

Example:

```python
class MemoryRepository:

    async def create(self, memory):
        ...

    async def search_candidates(self, user_id, query):
        ...

    async def update(self, memory):
        ...

    async def archive(self, memory_id):
        ...

    async def delete(self, memory_id):
        ...
```

Semantic vector search belongs to the Memory Service/vector layer.

---

# 59. Document Repository

Example:

```python
class DocumentRepository:

    async def create(self, document):
        ...

    async def get(self, document_id):
        ...

    async def list_accessible(self, user_id):
        ...

    async def update_status(self, document_id, status):
        ...

    async def create_version(self, version):
        ...
```

---

# 60. Execution Repository

Agent and tool execution repositories should support:

```text
create
update_status
get
list_by_conversation
list_by_user
list_children
```

This supports debugging and audit reconstruction.

---

# 61. Database Layer Structure

Recommended:

```text
backend/
└── app/
    ├── db/
    │   ├── session.py
    │   ├── base.py
    │   ├── models/
    │   │   ├── user.py
    │   │   ├── conversation.py
    │   │   ├── message.py
    │   │   ├── memory.py
    │   │   ├── document.py
    │   │   ├── execution.py
    │   │   ├── audit.py
    │   │   └── configuration.py
    │   │
    │   ├── repositories/
    │   └── migrations/
    │
    └── services/
```

---

# 62. SQLAlchemy

SQLAlchemy may be used as the ORM/DB abstraction.

Recommended separation:

```text
Domain Models
      |
Repository
      |
SQLAlchemy
      |
SQLite
```

Do not allow SQLAlchemy models to leak into the entire application.

---

# 63. Concurrency

SQLite has limitations around concurrent writes.

The implementation should:

* keep transactions short
* avoid long-running transactions
* use WAL mode where appropriate
* avoid holding database locks during model inference
* avoid holding transactions during document embedding
* use background workers for expensive processing

Recommended:

```text
PRAGMA journal_mode=WAL;
```

where appropriate for the deployment.

---

# 64. Long-Running Operations

Never do this:

```text
BEGIN TRANSACTION

Run LLM inference
Wait 20 seconds
Write result

COMMIT
```

Instead:

```text
Create execution record
      |
COMMIT
      |
Run inference
      |
Update execution
      |
COMMIT
```

The database should not be locked while the model is generating.

---

# 65. Conversation Write Flow

```text
User Message
    |
    v
Create Message
    |
    v
Commit
    |
    v
Context Engine
    |
    v
Agent Runtime
    |
    v
Model
    |
    v
Assistant Message
    |
    v
Commit
```

---

# 66. Agent Execution Write Flow

```text
Create AgentExecution
        |
        v
COMMIT
        |
        v
Agent Processing
        |
        +--> ToolExecution
        |
        +--> RAG
        |
        +--> Model
        |
        v
Update AgentExecution
        |
        v
COMMIT
```

---

# 67. Audit Write Flow

Audit events should be generated by application services rather than individual UI components.

Example:

```text
Document Service
      |
      v
Audit Service
      |
      v
AuditEvent
```

This ensures consistent audit behavior.

---

# 68. Security Boundaries

The database layer must not assume that an ID supplied by a client is authorized.

For example:

```text
GET /conversations/{id}
```

does not mean:

```text
SELECT conversation WHERE id = id
```

It means:

```text
Authenticate user
      |
Authorize resource
      |
Retrieve authorized record
```

Authorization remains a service/security concern.

---

# 69. Sensitive Data

Avoid storing:

* plaintext passwords
* API keys
* model credentials
* database credentials
* encryption keys
* unnecessary secrets
* unnecessary raw prompts

Sensitive configuration should be externalized.

---

# 70. Backup

The local deployment should support database backup.

For SQLite:

```text
mrpl.db
```

should be backed up using SQLite-safe backup mechanisms rather than blindly copying an actively written database file.

Vector store data and uploaded documents must also be included in backup planning.

---

# 71. Restore

A complete platform restore requires:

```text
SQLite database
+
Document storage
+
Vector store
+
Configuration
```

Restoring only the SQLite database may produce missing vector/document references.

Therefore backup architecture must treat these as one logical persistence system.

---

# 72. Data Lifecycle

Example document lifecycle:

```text
Upload
 |
 v
Document Created
 |
 v
Version Created
 |
 v
Chunks Created
 |
 v
Vectors Indexed
 |
 v
INDEXED
 |
 +--> New Version
 |
 +--> ARCHIVED
 |
 +--> DELETED
```

Memory lifecycle:

```text
Candidate
 |
 v
Validated
 |
 v
ACTIVE
 |
 +--> STALE
 +--> CONFLICTED
 +--> ARCHIVED
 +--> DELETED
```

Execution lifecycle:

```text
PENDING
 |
 v
RUNNING
 |
 +--> COMPLETED
 +--> FAILED
 +--> CANCELLED
 +--> TIMED_OUT
```

---

# 73. Data Ownership

Every user-scoped entity must have an explicit ownership or authorization relationship.

Examples:

```text
Conversation -> user_id
Memory -> user_id
Document -> owner_id
AgentExecution -> user_id
ToolExecution -> user_id
AuditEvent -> user_id
```

System-level records may have:

```text
user_id = NULL
```

where appropriate.

---

# 74. Cross-User Isolation

The application must prevent:

```text
User A
  |
  X
User B's conversation

User A
  |
  X
User B's memory

User A
  |
  X
Restricted document
```

Isolation must be enforced at service/repository boundaries.

---

# 75. Data Model and Context Engine

The Context Engine consumes:

```text
Messages
ConversationSummary
Memory
DocumentChunk metadata
ToolExecution results
AgentExecution state
```

But it should never bypass repositories.

```text
Context Engine
      |
      +--> Conversation Service
      +--> Memory Service
      +--> RAG Service
      +--> Tool Service
      +--> Execution Service
```

---

# 76. Data Model and RAG

RAG uses:

```text
Document
   |
DocumentVersion
   |
DocumentChunk
   |
Vector Store
```

The vector store should always be traceable back to:

```text
document_id
version_id
chunk_id
```

This is necessary for citations and audit.

---

# 77. Data Model and Memory

Memory uses:

```text
Memory
   |
   +--> metadata
   +--> lifecycle
   +--> ownership
   +--> embedding reference
```

The Context Engine retrieves semantic candidates.

Memory remains separate from RAG.

---

# 78. Data Model and Agent Harness

The Agent Harness creates:

```text
AgentExecution
```

and may create:

```text
ToolExecution
WorkflowExecution
```

The Harness must not directly manipulate database tables.

It should use execution services/repositories.

---

# 79. Data Model and Audit

The audit subsystem should correlate:

```text
user_id
conversation_id
agent_execution_id
tool_execution_id
workflow_execution_id
resource_id
```

This enables execution reconstruction.

---

# 80. Recommended Initial Schema

The initial implementation should prioritize these tables:

```text
users
conversations
messages
conversation_summaries
memories
documents
document_versions
document_chunks
agent_executions
tool_executions
audit_events
workflow_executions
model_configurations
```

Additional tables can be added when required.

Do not prematurely create dozens of microservice-style tables.

---

# 81. Example Relational Structure

```text
users
  |
  +---- conversations
  |          |
  |          +---- messages
  |          |
  |          +---- conversation_summaries
  |          |
  |          +---- agent_executions
  |                         |
  |                         +---- tool_executions
  |
  +---- memories
  |
  +---- documents
             |
             +---- document_versions
                         |
                         +---- document_chunks

workflow_executions
        |
        +---- agent_execution

audit_events
        |
        +---- user
        +---- conversation
        +---- agent_execution
        +---- tool_execution
```

---

# 82. Migration Order

Recommended initial migration order:

```text
1. users

2. conversations

3. messages

4. conversation_summaries

5. memories

6. documents

7. document_versions

8. document_chunks

9. agent_executions

10. tool_executions

11. workflow_executions

12. audit_events

13. model_configurations
```

Foreign-key dependencies must be respected.

---

# 83. Testing Requirements

Database tests must cover:

### User

* creation
* uniqueness
* activation/deactivation

### Conversation

* ownership
* creation
* archival
* isolation

### Messages

* ordering
* persistence
* role validation

### Memory

* lifecycle
* ownership
* status changes

### Documents

* duplicate detection
* versions
* status transitions

### Chunks

* ordering
* source metadata
* document relationship

### Executions

* lifecycle
* parent/child relationships
* failure state

### Audit

* append-only behavior
* correlation
* timestamps

---

# 84. Integration Tests

The system should test complete flows.

Example:

```text
User
 |
 v
Create conversation
 |
 v
Send message
 |
 v
Agent execution
 |
 v
RAG retrieval
 |
 v
Tool execution
 |
 v
Model response
 |
 v
Persist assistant message
 |
 v
Audit event
```

After completion, all expected records should exist.

---

# 85. Data Integrity Tests

Test cases should include:

```text
Invalid foreign key
Duplicate username
Duplicate conversation sequence
Invalid document version
Missing chunk
Invalid execution state
Unauthorized resource
Concurrent message creation
Database restart during operation
Partial ingestion failure
```

---

# 86. Recovery Requirements

If the application crashes during:

### Conversation

Messages already committed must remain.

### Agent execution

Execution should remain marked:

```text
RUNNING
```

until a recovery process determines whether it should become:

```text
FAILED
```

or:

```text
TIMED_OUT
```

### Document ingestion

A document stuck in:

```text
PROCESSING
```

should be recoverable/retryable.

---

# 87. No Orphaned Records

Foreign keys and cleanup logic should prevent uncontrolled orphaned:

```text
messages
chunks
tool executions
workflow executions
```

records.

Where historical audit requires records to survive deletion of parent resources, the schema should intentionally support that behavior rather than relying on accidental orphaning.

---

# 88. Performance Principles

The database should handle:

* thousands of conversations
* large message histories
* thousands of documents
* many document chunks
* many agent executions
* many audit records

without requiring premature distributed databases.

Optimization should be driven by measurements.

---

# 89. SQLite Production Considerations

SQLite is appropriate for:

* local deployment
* prototype
* single-node deployment
* moderate concurrency
* sovereign environments

If future deployments require:

* many concurrent writers
* multiple backend replicas
* centralized multi-user infrastructure
* very large operational datasets

then PostgreSQL may become appropriate.

The application should be prepared for that migration through repository abstraction.

---

# 90. Final Data Architecture

```text
                       MRPL WORKBENCH
                              |
                              v
                       Service Layer
                              |
                              v
                      Repository Layer
                              |
                              v
                           SQLite
                              |
       +----------+-----------+-----------+-----------+
       |          |           |           |           |
       v          v           v           v           v
    Users     Conversations Memory     Documents   Executions
                 |             |            |           |
                 v             v            v           v
              Messages      Embeddings   Chunks      Tools
                 |
                 v
             Summaries

                              |
                              v
                         Audit Events

                              |
                              v
                       Vector Store
                              |
                              +--> Document embeddings
                              +--> Memory embeddings
```

---

# 91. Critical Architectural Rules

The implementation must follow these rules:

1. **SQLite is the initial authoritative relational database.**

2. **Business logic must not directly depend on SQLite.**

3. **Repository abstractions must be used.**

4. **Complete conversation history must be persisted.**

5. **Complete history must not automatically be sent to the LLM.**

6. **Conversation summaries are derived data, not authoritative history.**

7. **Semantic memory and RAG documents must remain separate concepts.**

8. **Document metadata belongs in the relational database.**

9. **Document chunks must retain source/version relationships.**

10. **Vector records must be traceable to relational entities.**

11. **Document versions must be explicitly represented.**

12. **Document ingestion must be idempotent.**

13. **Agent executions must have explicit lifecycle states.**

14. **Tool executions must be independently auditable.**

15. **Workflow executions must be correlated with agent executions where applicable.**

16. **Audit records should be append-only.**

17. **Passwords must never be stored in plaintext.**

18. **Secrets must not be stored casually in database records.**

19. **Authorization must be enforced before resource retrieval.**

20. **User data must be isolated.**

21. **Long-running model inference must never hold database transactions open.**

22. **Database transactions should remain short.**

23. **SQLite foreign keys must be enabled.**

24. **Schema changes must use migrations.**

25. **Backups must include relational data, documents, and vector indexes as a coherent persistence system.**

26. **The data model must remain independent of Qwen, Llama, Ollama, or vLLM.**

27. **The data model must remain independent of Chroma, Qdrant, or FAISS.**

28. **The data model must support future migration to PostgreSQL.**

29. **No database schema should be created merely because a component might exist in the future.**

30. **Persistent data must remain traceable, auditable, and recoverable.**

---

# 92. Acceptance Criteria

The implementation is considered complete when:

* [ ] SQLite database is initialized automatically.
* [ ] Database location is configurable.
* [ ] SQLAlchemy/repository abstraction is implemented.
* [ ] Users can be persisted.
* [ ] Conversations can be persisted.
* [ ] Complete messages can be persisted.
* [ ] Conversation summaries can be persisted.
* [ ] Semantic memories can be persisted.
* [ ] Documents can be persisted.
* [ ] Document versions can be persisted.
* [ ] Document chunks can be persisted.
* [ ] Agent executions can be persisted.
* [ ] Tool executions can be persisted.
* [ ] Workflow executions can be persisted.
* [ ] Audit events can be persisted.
* [ ] Model configurations can be persisted.
* [ ] Foreign-key relationships are enforced.
* [ ] Appropriate indexes exist.
* [ ] User-level isolation is enforced.
* [ ] Document checksum/deduplication works.
* [ ] Document versioning works.
* [ ] Execution lifecycle states are persisted.
* [ ] Audit records are append-oriented.
* [ ] Database migrations are supported.
* [ ] Backup/restore strategy exists.
* [ ] Database failure handling is implemented.
* [ ] Repository interfaces are testable independently.
* [ ] SQLite can eventually be replaced without rewriting service logic.

---

# 93. Relationship to Other Documents

This document integrates with:

```text
REQUIREMENT.md
ARCHITECTURE.md
RAG_DESIGN.md
MEMORY_DESIGN.md
AGENT_DESIGN.md
SECURITY.md
EVALUATION.md
IMPLEMENTATION_PLAN.md
TOOL_MCP_DESIGN.md
CONTEXT_ENGINE_DESIGN.md
```

It provides the persistence foundation for:

```text
AGENT_HARNESS_DESIGN.md
MODEL_GATEWAY_DESIGN.md
API_DESIGN.md
MULTIMODAL_DESIGN.md
WORKFLOW_DESIGN.md
DEPLOYMENT_DESIGN.md
OBSERVABILITY_DESIGN.md
TESTING_STRATEGY.md
```

The database is therefore a foundational infrastructure component rather than merely a storage utility.

---

# 94. Final Design Principle

The MRPL Workbench must treat persistent data as **structured, authoritative, traceable state**.

The model reasons over context.

The vector store enables retrieval.

The agent runtime coordinates execution.

But the database remains the authoritative record of:

```text
who
did what
when
to which resource
during which conversation
using which agent
using which tool
with which execution state
```

This separation is essential for sovereignty, reproducibility, security, debugging, and long-term maintainability.
