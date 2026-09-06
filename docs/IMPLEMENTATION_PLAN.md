# MRPL Sovereign On-Premise Agentic AI Workbench

# Implementation Plan

## 1. Purpose

This document defines the recommended implementation sequence for the MRPL AI Workbench.

Implementation must follow the architecture contracts defined by the other design documents. Features should be integrated incrementally rather than building the entire agentic stack simultaneously.

---

## 2. Implementation Strategy

The recommended strategy is a vertical slice followed by progressive subsystem expansion.

Initial vertical slice:

```text
Login
  ↓
Conversation
  ↓
Agent
  ↓
Context Engine
  ↓
Model Gateway
  ↓
Local Model
  ↓
Persisted Message
```

Once this path is stable, add:

```text
RAG
Memory
Tools/MCP
Workflows
Multimodal
Observability
Hardening
```

This approach ensures that every major subsystem is connected to a working end-to-end path.

---

## 3. Phase 0 — Repository Foundation

Establish:

- backend structure
- frontend structure
- configuration management
- Docker Compose
- persistent data directories
- environment handling
- development scripts
- documentation conventions

Definition of done:

- project starts reproducibly
- configuration is externalized
- persistent storage survives container restart

---

## 4. Phase 1 — Persistence and Authentication

Implement:

- SQLite database
- repository layer
- users
- authentication
- sessions/tokens
- authorization primitives
- conversations
- messages
- audit-event persistence

Definition of done:

```text
User -> Login -> Authenticated Session -> Conversation -> Persisted Message
```

---

## 5. Phase 2 — Model Gateway

Implement the provider-independent model interface.

Required capabilities:

- text generation
- streaming
- embeddings
- vision where supported
- structured output where supported
- model discovery
- timeout handling
- error normalization

Implement the first local provider adapter.

The application must communicate with the model only through the gateway.

---

## 6. Phase 3 — Context Engine

Implement:

- token budgeting
- context prioritization
- recent-message selection
- conversation summarization
- RAG context slots
- memory slots
- tool-result slots
- deduplication
- permission filtering
- context-overflow protection
- source traceability

Definition of done:

```text
Agent Request
    -> Context Engine
    -> bounded ContextPackage
    -> Model Gateway
```

---

## 7. Phase 4 — Agent Harness

Implement:

- agent definitions
- agent versioning
- lifecycle
- execution state
- execution loop
- stop conditions
- timeout
- cancellation
- step limits
- model invocation
- structured execution events

The harness must remain the controller of agent execution.

---

## 8. Phase 5 — RAG

Implement:

- document ingestion
- parsing
- normalization
- chunking
- embeddings
- vector storage
- metadata
- semantic retrieval
- filtering
- reranking where required
- source references
- ingestion status

The relational database remains authoritative for document metadata.

---

## 9. Phase 6 — Memory

Implement the memory layers defined by the Memory Design.

Required capabilities:

- complete conversation persistence
- recent context
- summaries
- semantic memories
- memory retrieval
- memory updates/invalidation
- conflict handling
- permission filtering

The Context Engine remains responsible for deciding what memory enters a model request.

---

## 10. Phase 7 — Tools and MCP

Implement:

- tool registry
- typed schemas
- validation
- authorization
- execution limits
- tool-result normalization
- audit events
- MCP adapter

Start with safe read-only capabilities.

Do not expose arbitrary shell, SQL, filesystem, or network operations to the model.

---

## 11. Phase 8 — Workflow Integration

Implement the workflow service and n8n adapter.

Required controls:

- registered workflow IDs
- explicit agent permissions
- input validation
- execution timeout
- status tracking
- audit events
- result normalization

Agents must never receive unrestricted n8n access.

---

## 12. Phase 9 — Multimodal

Add:

- image input
- PDF/document processing
- OCR where required
- multimodal context representation
- capability-aware model routing

The Model Gateway must determine whether the selected local model supports the required modality.

---

## 13. Phase 10 — Frontend

Implement UI surfaces for:

- authentication
- chat
- conversations
- documents
- agents
- workflows
- execution status
- sources/citations
- administration
- settings

The frontend must communicate through the API rather than bypassing backend security boundaries.

---

## 14. Phase 11 — Observability

Implement:

- structured logs
- correlation IDs
- health checks
- metrics
- execution traces
- audit views
- model usage measurements
- RAG measurements
- tool/workflow execution measurements

Sensitive prompt and document content must not be logged by default.

---

## 15. Phase 12 — Security Hardening

Validate:

- authentication
- authorization
- session security
- data isolation
- prompt-injection resistance
- tool security
- file validation
- secret handling
- network restrictions
- container permissions
- dependency security
- resource limits

Run security tests before production packaging.

---

## 16. Phase 13 — Testing and Evaluation

Complete:

- unit tests
- component tests
- contract tests
- integration tests
- end-to-end tests
- security tests
- model evaluations
- RAG evaluations
- agent evaluations
- regression evaluations
- performance benchmarks

Maintain a versioned baseline.

---

## 17. Phase 14 — Deployment

Finalize:

- Docker images
- Compose deployment
- persistent volumes
- configuration
- health checks
- backups
- upgrade procedures
- rollback procedures
- model asset management
- operational documentation

The deployment must work without mandatory cloud dependencies.

---

## 18. Recommended Dependency Order

```text
Persistence
    ↓
Authentication
    ↓
API
    ↓
Model Gateway
    ↓
Context Engine
    ↓
Agent Harness
    ↓
RAG
    ↓
Memory
    ↓
Tools/MCP
    ↓
Workflow
    ↓
Multimodal
    ↓
Frontend integration
    ↓
Observability
    ↓
Security hardening
    ↓
Testing/Evaluation
    ↓
Deployment
```

Some activities may proceed in parallel after their contracts are stable.

---

## 19. Definition of Done

The platform should not be considered complete merely because the UI can generate an answer.

A release candidate must demonstrate:

- local model inference
- authenticated access
- persistent conversations
- bounded context construction
- working agent execution
- RAG with source traceability
- persistent memory
- controlled tools
- controlled workflows
- multimodal capability detection
- security enforcement
- auditability
- observability
- automated tests
- evaluation results
- reproducible deployment

---

## 20. Architectural Rule

Implementation must not bypass subsystem boundaries for convenience.

Examples:

```text
Do not:
Agent -> Ollama directly

Use:
Agent -> Agent Harness -> Model Gateway -> Provider Adapter
```

```text
Do not:
Agent -> Vector DB directly

Use:
Agent -> Context Engine -> RAG
```

```text
Do not:
LLM -> arbitrary shell

Use:
LLM -> Agent Harness -> Tool Registry -> Authorized Tool
```

These boundaries are essential for provider replacement, security, testing, and long-term maintainability.
