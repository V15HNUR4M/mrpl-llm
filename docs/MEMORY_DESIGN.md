# MRPL Private AI — Memory Design

## 1. Purpose

The MRPL Private AI system must maintain useful conversational context across turns and sessions without continuously sending the entire conversation history to the language model.

The memory system is responsible for:

* Maintaining short-term conversational context.
* Persisting complete conversation history.
* Creating compact summaries of older conversations.
* Extracting important facts and events into semantic memory.
* Retrieving relevant memories for future queries.
* Managing context-window and token limits.
* Detecting stale or conflicting memories.
* Separating conversational memory from MRPL document knowledge.
* Providing the Agent Harness with a controlled context package before every model invocation.

The memory system is an application-level subsystem. It does not modify the neural architecture of the underlying LLM.

---

# 2. Design Principles

The memory architecture follows these principles:

1. **Store more than we send.**
2. **Never send unlimited conversation history to the LLM.**
3. **Retrieve only context relevant to the current task.**
4. **Separate conversation memory from organizational knowledge.**
5. **Keep memory persistent across application restarts.**
6. **Make memory explainable and auditable.**
7. **Allow memories to be updated or invalidated.**
8. **Respect user and document permissions.**
9. **Keep the memory implementation independent of the underlying LLM.**
10. **Use the context manager as the only component responsible for assembling model context.**

---

# 3. Memory Architecture

The system uses four logical memory tiers.

```text
                    ┌───────────────────────────┐
                    │       Current Request     │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │      Context Manager      │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
       Working Memory      Conversation Memory   Semantic Memory
              │                   │                   │
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                                  ▼
                         MRPL Knowledge RAG
```

The four tiers are:

### Tier 1 — Working Memory

Temporary context for the current task.

### Tier 2 — Conversation Memory

Persistent messages and conversation summaries.

### Tier 3 — Semantic Long-Term Memory

Important facts extracted from conversations and stored for semantic retrieval.

### Tier 4 — MRPL Knowledge Base

Documents, manuals, reports, procedures and other organizational knowledge retrieved through RAG.

Tier 4 is intentionally kept separate from conversational memory.

---

# 4. Working Memory

Working memory represents the context required to solve the current request.

It is short-lived and reconstructed for every model invocation.

Typical contents include:

* Current user message.
* Recent conversation messages.
* Current agent task.
* Current subtask.
* Tool results.
* Relevant retrieved memories.
* Relevant RAG results.
* Current reasoning state where appropriate.
* Relevant system instructions.

Working memory should not be treated as permanent storage.

---

# 5. Recent Conversation Memory

The most recent messages are retained directly because they usually contain the strongest immediate conversational context.

Example:

```text
User:
What issue was found near the mechanical seal?

Assistant:
Minor leakage was observed.

User:
What should be done about it?
```

The second request depends heavily on the previous turn.

The context manager should therefore include recent messages directly.

A configurable number of recent messages should be retained rather than using an unlimited history.

Example configuration:

```text
RECENT_MESSAGE_COUNT = 10
```

The exact value must remain configurable.

---

# 6. Persistent Conversation History

Every user and assistant message should be persisted.

Conversation history exists independently of the context sent to the LLM.

Example:

```text
Conversation
    │
    ├── Message 1
    ├── Message 2
    ├── Message 3
    ├── Message 4
    ├── ...
    └── Message N
```

The database therefore acts as the authoritative record of the conversation.

The model does not need to receive all of these messages.

---

# 7. Conversation Summaries

When conversations become large, older messages should be compressed into a conversation summary.

Example:

```text
Messages 1–30
      ↓
Conversation Summary
      ↓
Messages 31–40
      ↓
Current Request
```

A summary should preserve:

* Important user goals.
* Decisions made.
* Relevant technical facts.
* Important entities.
* Previous conclusions.
* Unresolved questions.
* Important constraints.
* References to important documents.
* Important tool results.

A summary should not preserve unnecessary conversational filler.

---

# 8. Incremental Summarization

The system should not repeatedly summarize the entire conversation from scratch.

Instead:

```text
Existing Summary
      +
Older Messages
      ↓
Updated Summary
```

This reduces computational and token overhead.

A configurable summarization threshold should determine when summarization occurs.

Example:

```text
SUMMARY_TRIGGER_MESSAGES = 20
```

The exact threshold must be configurable.

---

# 9. Semantic Long-Term Memory

Semantic memory stores information that may remain useful beyond the current conversation.

Examples:

```text
User frequently works with MRPL maintenance documents.

User previously selected Qwen as the preferred local model.

A particular maintenance report was previously discussed.

A recurring project requirement was identified.
```

Semantic memory should contain information that is useful for future retrieval rather than duplicating every conversation message.

---

# 10. Memory Extraction

Important memories can be extracted from conversations periodically.

The extraction process should identify:

* Stable facts.
* Important preferences.
* Project decisions.
* Important technical conclusions.
* Recurring entities.
* Important unresolved tasks.
* Significant events.
* Useful references.

The extractor should avoid storing:

* Casual conversation.
* Temporary statements.
* Duplicate information.
* Sensitive information unless explicitly permitted.
* Entire conversation transcripts.
* Information with no expected future value.

---

# 11. Memory Representation

A semantic memory record should conceptually contain:

```text
Memory
├── id
├── user_id
├── conversation_id
├── content
├── memory_type
├── importance
├── confidence
├── embedding
├── created_at
├── updated_at
├── last_accessed_at
├── access_count
├── status
└── metadata
```

Possible memory types:

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

Possible statuses:

```text
ACTIVE
STALE
CONFLICTED
ARCHIVED
DELETED
```

---

# 12. Memory Importance

Every extracted memory should receive an importance score.

Example conceptual scale:

```text
0.0 ─────────────── 1.0
low                 high
```

High-importance memories should be more likely to be retrieved.

Importance can consider:

* Explicit user emphasis.
* Relevance to ongoing projects.
* Frequency of reuse.
* Recency.
* Persistence.
* Confidence.
* Number of successful retrievals.

The scoring implementation should remain replaceable.

---

# 13. Memory Confidence

Memories should also have a confidence score.

For example:

```text
confidence = 0.92
```

Low-confidence memories should not automatically influence high-impact decisions.

Confidence may be derived from:

* Explicit user statement.
* Extraction certainty.
* Repeated confirmation.
* Source reliability.
* Conflict detection.

---

# 14. Semantic Retrieval

When a new request arrives, the request is embedded and compared against stored semantic memories.

Conceptually:

```text
Current Request
      ↓
Embedding
      ↓
Vector Search
      ↓
Candidate Memories
      ↓
Relevance Filtering
      ↓
Context Manager
```

Only relevant memories should enter the model context.

---

# 15. Similarity Search

The semantic memory subsystem should support vector similarity search.

The implementation may initially use a local vector-capable database or vector extension.

The abstraction should remain:

```text
MemoryStore.search(
    query_embedding,
    top_k,
    filters
)
```

The memory system must not be tightly coupled to one vector database implementation.

---

# 16. jcode-Inspired Memory Model

The jcode harness provides useful architectural inspiration for semantic memory.

The relevant concept is:

```text
Every turn
    ↓
Semantic representation
    ↓
Memory retrieval
    ↓
Relevant memories
    ↓
Conversation context
```

The MRPL implementation should adopt the concept rather than blindly copying the implementation.

Useful jcode-inspired capabilities include:

* Semantic retrieval of previous interactions.
* Session search.
* Persistent memory.
* Explicit memory operations.
* Memory consolidation.
* Relevance-based context injection.

The MRPL system must remain independently structured and must not become dependent on jcode.

---

# 17. Memory Consolidation

Memory consolidation periodically reviews stored memories.

The purpose is to:

* Remove duplicates.
* Merge related memories.
* Detect contradictions.
* Update stale memories.
* Archive obsolete memories.
* Improve memory quality.

Conceptually:

```text
Memory A
Memory B
Memory C
      ↓
Consolidation
      ↓
Canonical Memory
```

Example:

```text
Memory A:
User prefers Qwen.

Memory B:
Qwen was selected as the primary prototype model.

Memory C:
Project uses Qwen locally.

Possible consolidated memory:
Qwen is currently the preferred local model for the MRPL prototype.
```

---

# 18. Conflict Detection

The system must not silently overwrite contradictory memories.

Example:

```text
Old:
Primary model = Llama

New:
Primary model = Qwen
```

The system should identify the conflict.

Possible resolution:

```text
Old Memory → STALE
New Memory → ACTIVE
```

However, automatic conflict resolution should only occur when confidence is sufficiently high.

Otherwise:

```text
CONFLICTED
```

The system may request confirmation when necessary.

---

# 19. Memory Freshness

Memories may become outdated.

Each memory should therefore track:

```text
created_at
updated_at
last_accessed_at
```

The system may use freshness when ranking memories.

A useful conceptual score is:

```text
Memory Score =
    semantic_similarity
    × importance
    × confidence
    × freshness
```

The exact formula is implementation-specific.

---

# 20. Memory Deduplication

Before creating a new memory, the system should check for semantically similar existing memories.

Example:

```text
Existing:
The project uses SQLite.

New:
SQLite is being used as the project's local database.
```

These should not necessarily become two independent memories.

The system should attempt to update or consolidate the existing memory.

---

# 21. Conversation Memory vs RAG

Conversation memory and RAG must remain separate.

### Conversation Memory

Answers:

> What did we discuss before?

Examples:

* Previous decisions.
* User goals.
* Previous interactions.
* Important project context.

### RAG

Answers:

> What does the organization's knowledge base say?

Examples:

* Maintenance manuals.
* Inspection reports.
* SOPs.
* Technical documents.
* Company policies.

Architecture:

```text
             Current Request
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
     Memory Retrieval     RAG Retrieval
          │                   │
          ▼                   ▼
 Conversation Context   Document Context
          │                   │
          └─────────┬─────────┘
                    ▼
             Context Manager
                    │
                    ▼
                   LLM
```

---

# 22. Context Manager

The Context Manager is the central component responsible for constructing the prompt context.

No other component should independently decide what historical context is sent to the model.

Input:

```text
Current Request
Conversation ID
User ID
Agent Task
```

Output:

```text
Model Context Package
```

---

# 23. Context Assembly

A typical context assembly process is:

```text
1. Load system instructions
2. Load current request
3. Load recent messages
4. Load conversation summary
5. Retrieve relevant semantic memories
6. Retrieve relevant RAG context
7. Add required tool information
8. Apply permissions
9. Apply token budget
10. Produce final model context
```

---

# 24. Token Budget

The context manager must operate within the configured model context window.

Example:

```text
Model Context Window
        │
        ├── System Instructions
        ├── Recent Messages
        ├── Summary
        ├── Semantic Memory
        ├── RAG Context
        ├── Tool Definitions
        └── Output Reservation
```

The system must reserve sufficient tokens for the model's response.

The context manager must never assume that all available tokens can be consumed by retrieved context.

---

# 25. Priority-Based Context Selection

When context exceeds the available budget, information should be removed according to priority.

Suggested priority:

```text
1. Current request
2. Required system instructions
3. Critical tool information
4. Recent conversation
5. Relevant RAG context
6. Relevant semantic memories
7. Conversation summary
8. Lower-priority historical information
```

The exact ranking should remain configurable.

---

# 26. Context Compression

If relevant information cannot fit within the model context window, the system may compress it.

Possible strategies:

```text
Long conversation
      ↓
Summary

Large RAG result
      ↓
Relevant passage extraction

Many memories
      ↓
Top-K ranking

Large tool output
      ↓
Structured compression
```

The system should prefer compression and ranking over blindly truncating text.

---

# 27. Recursive Context Feeding

The system must NOT solve context limitations by continuously feeding chunks recursively to the model and expecting the model to maintain perfect state.

Instead:

```text
Large Information Set
        ↓
Chunking
        ↓
Retrieval
        ↓
Ranking
        ↓
Compression/Summarization
        ↓
Context Assembly
        ↓
LLM
```

Recursive processing may be used for specific document-analysis workflows, but it must not replace context management.

---

# 28. Memory Access

The Agent Harness should interact with memory through explicit interfaces.

Conceptual interface:

```python
class MemoryStore:

    def add(memory):
        ...

    def search(query, top_k):
        ...

    def update(memory_id, data):
        ...

    def archive(memory_id):
        ...

    def delete(memory_id):
        ...
```

The actual implementation can use SQLite plus a vector storage mechanism.

---

# 29. Explicit Memory Tools

Agents may need explicit memory operations.

Examples:

```text
remember
search_memory
update_memory
forget_memory
```

However, memory tools must be permission-controlled.

An agent must not be able to arbitrarily modify another user's memory.

---

# 30. User Isolation

Memory must be isolated by user.

Conceptually:

```text
User A
 ├── Conversations
 └── Memories

User B
 ├── Conversations
 └── Memories
```

A memory retrieval query must always include the appropriate authorization scope.

Example:

```text
WHERE user_id = current_user
```

Cross-user memory retrieval must be explicitly authorized.

---

# 31. Project-Level Memory

The system may support project-scoped memory.

Example:

```text
User
 ├── Personal Memory
 └── Project Memory
       ├── MRPL Project
       └── Other Project
```

Project memory should be permission-aware.

This allows multiple authorized users or agents to share relevant project context without exposing unrelated personal memory.

---

# 32. Agent Memory

Agent execution may maintain task-specific state.

Example:

```text
Supervisor Agent
      │
      ├── Document Agent state
      ├── Analysis Agent state
      └── Report Agent state
```

Agent state should be separated from long-term conversational memory.

Temporary execution state should not automatically become permanent memory.

---

# 33. Tool Results and Memory

Tool results should not automatically be stored as permanent memories.

Instead:

```text
Tool Result
    ↓
Evaluate usefulness
    ↓
If important
    ↓
Memory Extraction
    ↓
Persistent Memory
```

This prevents the memory database from filling with temporary tool outputs.

---

# 34. Memory Lifecycle

The complete lifecycle is:

```text
Conversation
     ↓
Memory Candidate Detection
     ↓
Extraction
     ↓
Validation
     ↓
Deduplication
     ↓
Storage
     ↓
Embedding
     ↓
Retrieval
     ↓
Usage
     ↓
Consolidation
     ↓
Update / Archive / Delete
```

---

# 35. Memory Retrieval Pipeline

```text
User Request
     ↓
Generate Query Embedding
     ↓
Search Semantic Memory
     ↓
Apply User/Project Permissions
     ↓
Calculate Relevance
     ↓
Apply Importance/Confidence/Freshness
     ↓
Select Top-K
     ↓
Context Manager
```

---

# 36. Memory Extraction Pipeline

```text
Conversation
     ↓
Determine whether extraction is required
     ↓
Extract candidate memories
     ↓
Validate candidates
     ↓
Check existing memories
     ↓
Detect duplicates/conflicts
     ↓
Create/update/archive
     ↓
Generate embeddings
```

---

# 37. Persistence

The initial implementation should prioritize SQLite because MRPL is designed as a local-first system.

Conceptual entities:

```text
users
conversations
messages
conversation_summaries
memories
memory_links
```

Possible `memories` structure:

```text
id
user_id
project_id
conversation_id
content
memory_type
importance
confidence
status
created_at
updated_at
last_accessed_at
access_count
metadata
embedding_reference
```

The physical schema may evolve during implementation.

---

# 38. Embedding Strategy

The memory subsystem should use a local embedding model.

No external embedding API should be required for normal operation.

The embedding model should be configurable independently of the generation model.

Example:

```text
Generation Model:
Qwen

Embedding Model:
Local embedding model
```

This allows generation and retrieval models to evolve independently.

---

# 39. Offline Requirement

The memory subsystem must continue functioning without external cloud APIs.

The intended architecture is:

```text
Local LLM
+
Local Embedding Model
+
Local Database
+
Local Vector Storage
```

Cloud APIs may optionally be supported through provider adapters, but they must not be required.

---

# 40. Failure Handling

If semantic retrieval fails:

```text
Memory Retrieval Failure
        ↓
Log failure
        ↓
Continue with recent history + summary
```

If memory extraction fails:

```text
Extraction Failure
        ↓
Log failure
        ↓
Conversation remains intact
```

Memory failure must never destroy the user's conversation.

If embeddings are unavailable:

```text
Fallback:
Recent messages
+
Conversation summary
+
Direct database retrieval where applicable
```

---

# 41. Observability

The memory system should record:

* Retrieval latency.
* Number of memories searched.
* Number of memories selected.
* Similarity scores.
* Memory creation events.
* Memory updates.
* Memory conflicts.
* Consolidation events.
* Context token estimates.
* Context truncation/compression events.

Sensitive memory contents should not unnecessarily appear in logs.

---

# 42. Auditability

Important memory mutations should be auditable.

Examples:

```text
MEMORY_CREATED
MEMORY_UPDATED
MEMORY_ARCHIVED
MEMORY_DELETED
MEMORY_CONFLICT_DETECTED
MEMORY_CONSOLIDATED
```

Audit records should include:

```text
timestamp
user
operation
memory_id
agent
request_id
result
```

---

# 43. Security

The memory subsystem must enforce:

* User isolation.
* Project permissions.
* Authentication.
* Authorization.
* No arbitrary cross-user retrieval.
* No unrestricted memory modification by agents.
* Audit logging for sensitive operations.

Memory retrieval must occur after authorization scope is established.

---

# 44. Context Package

The final object passed to the Model Gateway should conceptually contain:

```text
ContextPackage
├── system_instructions
├── current_request
├── recent_messages
├── conversation_summary
├── semantic_memories
├── rag_context
├── tools
├── agent_state
└── metadata
```

The Model Gateway receives this package and converts it into the format required by the selected model/provider.

---

# 45. Model Independence

The memory system must not assume:

* Qwen-specific APIs.
* Llama-specific APIs.
* Ollama-specific APIs.
* vLLM-specific APIs.

Instead:

```text
Memory
   ↓
Context Manager
   ↓
Model Gateway
   ↓
Provider Adapter
   ↓
Model Server
```

This ensures that the generation model can be replaced without redesigning memory.

---

# 46. Initial Implementation Strategy

Implementation should proceed incrementally.

### Phase 1

Implement:

* Message persistence.
* Conversation persistence.
* Recent-message retrieval.
* Basic context manager.

### Phase 2

Implement:

* Conversation summaries.
* Summary update mechanism.
* Token-aware context assembly.

### Phase 3

Implement:

* Local embeddings.
* Semantic memory storage.
* Semantic retrieval.

### Phase 4

Implement:

* Memory extraction.
* Deduplication.
* Importance/confidence scoring.

### Phase 5

Implement:

* Memory consolidation.
* Conflict detection.
* Staleness handling.

### Phase 6

Implement:

* Agent memory.
* Project memory.
* Explicit memory tools.

### Phase 7

Implement:

* Advanced evaluation.
* Retrieval metrics.
* Context optimization.
* Performance tuning.

---

# 47. Evaluation

Memory quality must be evaluated independently from generation quality.

Important metrics include:

### Retrieval Precision

How often retrieved memories are actually relevant.

### Retrieval Recall

How often useful memories are successfully retrieved.

### Context Efficiency

How much useful information is included per token.

### Memory Accuracy

Whether stored memories correctly represent the original information.

### Conflict Accuracy

Whether contradictory memories are correctly detected.

### Persistence

Whether memory survives application restarts.

### Isolation

Whether users can access only authorized memories.

---

# 48. Acceptance Criteria

The memory subsystem is considered complete when:

* Conversations persist across restarts.
* Recent messages are automatically restored.
* Older conversations can be summarized.
* Summaries are incorporated into future requests.
* Important memories can be extracted.
* Memories can be semantically retrieved.
* Memory retrieval is permission-aware.
* Duplicate memories can be detected.
* Conflicting memories can be detected.
* Stale memories can be handled.
* Context assembly respects token limits.
* RAG context remains separate from conversational memory.
* Agents can access memory through controlled interfaces.
* Memory failures do not destroy conversations.
* Memory operations are observable and auditable.
* The system works with local models.
* The memory subsystem is independent of the selected LLM provider.

---

# 49. Final Architecture

The intended final memory architecture is:

```text
                         USER REQUEST
                              │
                              ▼
                     ┌─────────────────┐
                     │  Context Manager│
                     └────────┬────────┘
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
   Recent Messages     Conversation Summary   Semantic Memory
          │                   │                    │
          │                   │             ┌──────┴──────┐
          │                   │             │ Vector Search│
          │                   │             └──────┬──────┘
          │                   │                    │
          └───────────────────┼────────────────────┘
                              │
                              ▼
                       Permission Filter
                              │
                              ▼
                         RAG Retrieval
                              │
                              ▼
                       Token Budgeting
                              │
                              ▼
                      Context Compression
                              │
                              ▼
                       Context Package
                              │
                              ▼
                        Model Gateway
                              │
                              ▼
                       Local Open-Weight LLM
```

The critical design rule is:

> **The database stores the conversation; semantic memory stores reusable knowledge extracted from the conversation; RAG stores organizational knowledge; and the Context Manager decides what the LLM actually sees.**

This architecture provides persistent conversational intelligence without requiring architectural changes to the underlying open-weight language model.
