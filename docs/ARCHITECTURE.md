# MRPL Sovereign On-Premise Agentic AI Workbench
# System Architecture

## 1. Architecture Philosophy

The MRPL AI Workbench is designed as a sovereign, modular, locally
deployable Agentic AI platform.

The architecture separates:

1. User interface
2. Application/API layer
3. Agent orchestration
4. Agent harness
5. Memory
6. RAG
7. Tool/MCP execution
8. Model serving
9. Persistence
10. Security
11. Audit
12. Workflow automation

No individual model, provider, agent, or workflow system should become
tightly coupled to the rest of the application.

The system should follow:

    Interface
        ↓
    Application Layer
        ↓
    Agent Runtime
        ↓
    Knowledge / Memory / Tools
        ↓
    Model Gateway
        ↓
    Local Model Server
        ↓
    Open-Weight Model

---

# 2. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                         MRPL AI WORKBENCH                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                         FRONTEND                           │  │
│  │                                                            │  │
│  │ Chat │ Documents │ Agents │ Workflows │ Admin │ Settings  │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                      API / APPLICATION                     │  │
│  │                                                            │  │
│  │ Auth │ Conversations │ Context │ Memory │ RAG │ Audit      │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                      AGENT RUNTIME                         │  │
│  │                                                            │  │
│  │                    Supervisor Agent                       │  │
│  │                           │                                │  │
│  │          ┌────────────────┼────────────────┐               │  │
│  │          ▼                ▼                ▼               │  │
│  │    Document Agent   Analysis Agent   Report/Tool Agent    │  │
│  └──────────┬────────────────┬────────────────┬───────────────┘  │
│             │                │                │                  │
│             ▼                ▼                ▼                  │
│       ┌──────────┐     ┌──────────┐    ┌──────────────┐         │
│       │   RAG    │     │  Memory  │    │ Tool / MCP   │         │
│       └──────────┘     └──────────┘    └──────┬───────┘         │
│                                                │                 │
│                                                ▼                 │
│                                           n8n / Tools            │
│                                                                  │
│                         MODEL GATEWAY                            │
│                               │                                  │
│                 ┌─────────────┴─────────────┐                   │
│                 ▼                           ▼                   │
│              Ollama                       vLLM                  │
│                 │                           │                    │
│                 └─────────────┬─────────────┘                    │
│                               ▼                                  │
│                       Open-Weight Models                         │
│                         Qwen / Llama / etc.                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

3. Architectural Layers
Layer 1 — Frontend

Technology:

React
TypeScript
Modern component-based UI

Responsibilities:

Chat interface
Conversation management
Document upload
Source display
Agent status
Tool execution status
Memory visibility where appropriate
Workflow status
Administration interface

The frontend must not implement security logic.

Security decisions must be enforced by the backend.

4. API / Application Layer

Initial technology:

Python
FastAPI

Responsibilities:

Authentication
Authorization
REST APIs
Conversation management
Document management
Agent invocation
Memory operations
RAG requests
Tool requests
Audit events
System configuration

The API layer coordinates application behavior but should not contain
the implementation details of individual AI agents.

5. Model Gateway

The Model Gateway is a mandatory architectural boundary.

Agents must never directly depend on Ollama, vLLM, Qwen, Llama, or
another specific model implementation.

Architecture:

Agent
  ↓
Model Gateway
  ↓
Provider Adapter
  ↓
Local Model Server
  ↓
Model

Potential providers:

Ollama
vLLM
LM Studio
Other OpenAI-compatible local endpoints

The initial implementation should prioritize Ollama because it provides
a simple local development path.

vLLM should remain a supported future/production-oriented provider.

6. Model Provider Interface

Conceptually:

ModelProvider

    generate()
    stream()
    embed()
    vision()
    tool_call()

Not every provider must implement every capability.

Capabilities should be detected/configured rather than assumed.

The application should be able to change:

Qwen

to:

Llama

without changing the agent architecture.

7. Agent Harness

The project will use a dedicated Agent Runtime/Harness layer.

The harness is responsible for generic agent execution capabilities:

Agent lifecycle
Sessions
Context construction
Tool invocation
Memory access
Model invocation
Agent-to-agent communication where required
Execution state
Error handling
Streaming

The harness should remain independent from MRPL-specific business logic
as much as practical.

8. jcode Relationship

jcode is treated as an architectural reference for the agent harness.

Relevant concepts identified from jcode include:

Session management
Semantic memory
Context-aware memory retrieval
Provider abstraction
Local model connectivity
Tool calling
MCP
Agent execution
Swarm/agent coordination
Server/client architecture
Adaptive context/file retrieval

The project must NOT blindly fork and convert jcode into MRPL.

Before importing any jcode implementation:

Understand the implementation.
Identify its dependencies.
Determine whether it solves an MRPL requirement.
Determine whether licensing permits reuse.
Determine whether integration introduces unnecessary complexity.
Prefer clean interfaces over tightly coupling MRPL to jcode internals.

The architecture should be jcode-inspired where useful rather than
jcode-dependent by default.

9. Agent Architecture

Initial agent topology:

                    ┌───────────────────┐
                    │ Supervisor Agent  │
                    └─────────┬─────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
   Document Agent      Analysis Agent       Report Agent
                                                  │
                                                  ▼
                                            Tool Agent

The Supervisor determines which capability is appropriate.

Agents must have explicit responsibilities.

10. Supervisor Agent

Responsibilities:

Understand the user's request.
Determine the required capability.
Select the appropriate agent/tool.
Provide required context.
Coordinate multi-step operations.
Validate results where appropriate.
Return the final response.

The Supervisor should not perform every task itself.

11. Document Agent

Responsibilities:

Query the MRPL knowledge base.
Retrieve relevant documents.
Construct RAG context.
Answer document-grounded questions.
Return source references.

Architecture:

User Query
    ↓
Document Agent
    ↓
Query Processing
    ↓
Vector Retrieval
    ↓
Optional Reranking
    ↓
Context Construction
    ↓
Model
    ↓
Answer + Sources
12. Analysis Agent

Responsibilities:

Analyze retrieved information.
Compare documents/data.
Perform structured reasoning.
Produce analytical conclusions.

The Analysis Agent may use:

RAG
Tools
Memory
Model reasoning
13. Report Agent

Responsibilities:

Generate structured reports.
Combine information from other agents.
Format results.
Invoke report-generation tools when required.
14. Tool Agent

The Tool Agent handles controlled external capabilities.

Architecture:

Agent
  ↓
Tool Registry
  ↓
Tool Validation
  ↓
Authorization
  ↓
Execution
  ↓
Result
  ↓
Agent

Tools must have explicit schemas.

15. Memory Architecture

Memory is divided into four conceptual layers.

┌───────────────────────────┐
│ Working Memory            │
│ Recent conversation       │
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Conversation Summary      │
│ Compressed older context  │
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Semantic Memory           │
│ Important facts/preferences│
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ MRPL Knowledge Base       │
│ Documents / RAG           │
└───────────────────────────┘

These layers must not be treated as identical data.

16. Context Manager

Every model request passes through a Context Manager.

Responsibilities:

Token budgeting
Recent-message selection
Conversation summary retrieval
Semantic-memory retrieval
RAG-context insertion
Tool-context insertion
System-prompt construction
Context truncation

Conceptual pipeline:

User Request
     ↓
Context Manager
     │
     ├── Recent Messages
     ├── Conversation Summary
     ├── Semantic Memory
     ├── RAG Results
     └── Tool Definitions
     ↓
Token Budgeting
     ↓
Final Model Context

The system must never blindly send unlimited conversation history.

17. RAG Architecture
                 DOCUMENT INGESTION

Document
   ↓
Parser
   ↓
Cleaner
   ↓
Chunker
   ↓
Metadata Extraction
   ↓
Embedding Model
   ↓
Vector Store


                  QUERY PIPELINE

User Query
   ↓
Query Embedding
   ↓
Vector Search
   ↓
Metadata / Permission Filtering
   ↓
Top-K Results
   ↓
Optional Reranking
   ↓
Context Builder
   ↓
Agent
   ↓
Model
18. Permission-Aware RAG

Document access must be checked before retrieved content is provided
to the model.

Conceptually:

Query
 ↓
Vector Search
 ↓
Permission Filter
 ↓
Allowed Documents
 ↓
Context
 ↓
LLM

The system must not retrieve restricted information and rely on the
LLM to decide whether to reveal it.

19. Tool Architecture

Tools should be centrally registered.

Example:

Tool Registry
│
├── search_documents
├── get_document
├── search_memory
├── store_memory
├── generate_report
├── get_equipment_status
└── create_workflow_request

Each tool should define:

Name
Description
Input schema
Output schema
Required permissions
Execution handler
Timeout
Audit requirements
20. MCP Architecture

MCP should expose controlled tools/capabilities.

MRPL Agent
    ↓
MCP Client
    ↓
MCP Server
    ↓
Controlled Tool
    ↓
Result

MCP must not bypass:

Authentication
Authorization
Audit
Tool validation
21. Workflow Automation

n8n is an execution/integration layer.

It is NOT the primary reasoning engine.

MRPL Agent
     ↓
Tool Abstraction
     ↓
Permission Check
     ↓
n8n Workflow
     ↓
Enterprise Action

Examples:

Report generation
Notification
Maintenance workflow
Controlled enterprise integration
22. Persistence Architecture

Initial database:

SQLite

Core entities:

User
Conversation
Message
ConversationSummary
Memory
Document
DocumentChunk
AuditEvent
ToolExecution
AgentExecution

Vector storage may be implemented separately depending on the selected
vector database/embedding architecture.

The persistence layer should use repository/service abstractions so
database technology can be changed later if required.

23. Security Architecture

Security boundaries:

User
 ↓
Authentication
 ↓
Authorization
 ↓
Application API
 ↓
Agent
 ↓
RAG / Tools / Memory

Every sensitive operation must verify authorization.

Security must not depend on frontend restrictions.

24. Audit Architecture

Every important AI operation should generate an audit event.

Example:

User
 ↓
Request
 ↓
Supervisor
 ↓
Agent
 ↓
RAG
 ↓
Tool
 ↓
Model
 ↓
Response

Relevant events should be recorded.

Audit information may include:

Timestamp
User
Conversation
Agent
Model
Tool
Sources
Action
Result
Failure reason
25. Multimodal Architecture

Multimodal requests should use the same model abstraction.

Image / Document / Text
          ↓
    Input Processor
          ↓
      Agent Runtime
          ↓
      Model Gateway
          ↓
Vision-capable Local Model

Multimodal support should be capability-driven.

If the selected model does not support vision, the system must handle
the capability limitation gracefully.

26. Deployment Architecture

Initial development:

Frontend
   ↓
Backend
   ↓
Ollama
   ↓
Open-Weight Model

Expanded deployment:

┌─────────────┐
│  Frontend   │
└──────┬──────┘
       ▼
┌─────────────┐
│   Backend   │
└──┬─────┬────┘
   │     │
   │     ├──────────────┐
   │     ▼              ▼
   │   Vector DB       n8n
   │
   ▼
Model Gateway
   │
   ▼
Ollama / vLLM
   │
   ▼
Local Model

Docker Compose should eventually provide reproducible deployment.

27. Data Flow — Normal Chat
User
 ↓
Frontend
 ↓
API
 ↓
Authentication
 ↓
Conversation Service
 ↓
Context Manager
 ├── Recent Messages
 ├── Summary
 └── Semantic Memory
 ↓
Supervisor
 ↓
Model Gateway
 ↓
Local Model
 ↓
Response
 ↓
Memory Extraction
 ↓
Persistence
 ↓
Frontend
28. Data Flow — RAG Query
User
 ↓
API
 ↓
Supervisor
 ↓
Document Agent
 ↓
Query Embedding
 ↓
Vector Search
 ↓
Permission Filtering
 ↓
Relevant Chunks
 ↓
Context Manager
 ↓
Local LLM
 ↓
Answer + Sources
 ↓
Audit
29. Data Flow — Tool Execution
User
 ↓
Supervisor
 ↓
Tool Decision
 ↓
Tool Validation
 ↓
Authorization
 ↓
Tool / MCP
 ↓
Execution
 ↓
Result
 ↓
Agent
 ↓
Local LLM
 ↓
Final Response
 ↓
Audit
30. Data Flow — Multi-Agent Task
User
 ↓
Supervisor
 ↓
Task Decomposition
 ↓
┌───────────────┬────────────────┐
▼               ▼                ▼
Document      Analysis         Report
Agent         Agent            Agent
│               │                │
└───────────────┴────────────────┘
                ↓
          Result Aggregation
                ↓
           Supervisor
                ↓
             User

Multi-agent execution should only be used when the task benefits from
specialization or parallel execution.

31. Error Handling

Every subsystem must fail gracefully.

Examples:

Model unavailable

Return a controlled service-unavailable error.

Vector database unavailable

Do not fabricate document-grounded answers.

Tool failure

Return the failure to the agent and allow recovery where appropriate.

Unauthorized request

Reject before sensitive information/tool execution is exposed.

Context overflow

Reduce context using the Context Manager.

32. Observability

The system should provide structured logs for:

API requests
Agent execution
Model requests
Retrieval
Tool execution
Errors
Authentication events

Logs must not expose:

Passwords
API keys
Tokens
Sensitive credentials
33. Technology Strategy

Initial preferred stack:

Frontend

React + TypeScript

Backend

Python + FastAPI

Database

SQLite

Model Serving

Ollama initially

vLLM as an alternative/production-oriented provider

Models

Qwen initially

Other open-weight models supported through the model gateway

Embeddings

A locally deployable embedding model

Vector Storage

Select the simplest suitable local vector store during implementation.

Agent Runtime

Custom MRPL agent runtime inspired by useful jcode concepts.

Workflow

n8n

Deployment

Docker + Docker Compose

34. Design Principle — Replaceability

The following must remain replaceable:

Qwen
 ↓
Llama
 ↓
Mistral

and:

Ollama
 ↓
vLLM

and potentially:

SQLite
 ↓
PostgreSQL

The rest of the architecture should not require major rewrites.

35. Design Principle — Least Privilege

Agents receive only the tools they need.

Tools receive only the permissions they need.

Users receive only the data/actions they are authorized to access.

No component should receive unrestricted system access merely for
convenience.

36. Design Principle — Local First

The default path should be:

MRPL
 ↓
Local Backend
 ↓
Local Agent Runtime
 ↓
Local RAG
 ↓
Local Memory
 ↓
Local Model

External services are optional integrations, not mandatory dependencies
for core AI functionality.

37. Implementation Rule

Implementation must proceed incrementally.

Each subsystem must be:

Designed
Implemented
Tested
Verified
Committed
Documented

before dependent subsystems are built.

No coding agent should rewrite the entire repository unless explicitly
authorized.

38. Architecture Acceptance Criteria

The architecture is considered valid when:

The model can be replaced without rewriting agents.
The model server can be replaced without rewriting agents.
RAG is independent from conversation memory.
Conversation history is persistent.
Context is dynamically constructed.
Agents have explicit responsibilities.
Tools require explicit authorization.
MCP does not bypass security.
n8n is an execution layer rather than the reasoning layer.
Audit records can reconstruct important AI operations.
Core inference works without mandatory cloud APIs.
The system can be deployed locally.
Components can be independently tested.