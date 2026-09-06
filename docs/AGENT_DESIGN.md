# MRPL Sovereign On-Premise Agentic AI Workbench

# Agent Design

## 1. Purpose

This document defines the logical design of an MRPL AI agent.

An agent is a versioned, policy-controlled runtime definition that combines:

- instructions
- model capabilities
- context requirements
- memory policy
- authorized tools
- authorized workflows
- execution limits
- output requirements

An agent does not directly own infrastructure resources. The Agent Harness executes the agent under platform security and runtime policies.

---

## 2. Architectural Position

```text
User Request
    |
    v
Application API
    |
    v
Agent Harness
    |
    +--> Agent Definition
    +--> Context Engine
    +--> Model Gateway
    +--> Memory
    +--> RAG
    +--> Tool Registry
    +--> Workflow Service
    |
    v
Agent Result
```

The Agent Design is declarative. Runtime state belongs to the Agent Harness.

---

## 3. Agent Definition

Each agent should have a versioned definition containing at least:

```text
agent_id
name
description
version
status
instructions
model_requirements
context_policy
memory_policy
tool_permissions
workflow_permissions
execution_limits
output_contract
owner
created_at
updated_at
```

Example conceptual definition:

```yaml
agent_id: document_agent
name: MRPL Document Agent
version: 1.0
status: enabled

model_requirements:
  capabilities:
    - text_generation

context_policy:
  rag: true
  conversation_memory: true
  semantic_memory: false

memory_policy:
  read: true
  write: false

tools:
  allowed:
    - document_search

workflows:
  allowed: []

execution_limits:
  max_steps: 8
  timeout_seconds: 120
```

The exact serialization format is an implementation decision; the logical fields are part of the contract.

---

## 4. Agent Identity

An agent identity must be stable and independently addressable.

Required properties:

- unique `agent_id`
- human-readable name
- description
- version
- owner
- lifecycle status

Agents must be versioned rather than silently modified while executions are in progress.

An execution should retain the agent version used for that execution.

---

## 5. Instructions

Instructions define the agent's role, objectives, constraints, and response behavior.

Instructions must be separated from:

- user input
- retrieved documents
- tool output
- memory
- external data

Retrieved content and tool results are untrusted data. They must never automatically become higher-priority instructions.

---

## 6. Model Requirements

Agents must describe required capabilities rather than hard-code a provider.

Example:

```text
required capabilities:
    text_generation
    structured_output
    vision
    tool_calling
```

The Agent Harness asks the Model Gateway for a compatible model.

This allows the same agent to operate with different local models such as Qwen or Llama when their capabilities satisfy the requirement.

---

## 7. Context Policy

An agent may specify which context sources it requires.

Possible sources:

- current request
- recent conversation
- conversation summary
- semantic memory
- RAG results
- tool results
- workflow results
- agent state
- system instructions

The Context Engine remains responsible for token budgeting, prioritization, deduplication, permission filtering, and final context construction.

The agent only declares requirements.

---

## 8. Memory Policy

Memory access must be explicit.

Possible permissions:

```text
NONE
READ
WRITE
READ_WRITE
```

An agent should not automatically receive every stored memory.

Memory retrieval must remain:

- relevant
- permission-aware
- traceable
- bounded

Memory writes should also be controlled because an incorrect model-generated statement must not automatically become trusted persistent knowledge.

---

## 9. Tool and Workflow Permissions

Agents receive explicit capability permissions.

Example:

```text
Document Agent
    -> document_search: allowed
    -> shell: denied
    -> raw_sql: denied
    -> arbitrary_http: denied
    -> maintenance_workflow: denied
```

Workflow access is similarly explicit.

The LLM may request a tool or workflow, but the platform performs authorization and validation before execution.

---

## 10. Execution Limits

Agents must have bounded execution.

Typical limits include:

- maximum steps
- maximum tool calls
- maximum workflow calls
- timeout
- maximum context size
- maximum output tokens
- maximum retry count
- resource limits

These limits prevent runaway agent loops and resource exhaustion.

---

## 11. Agent Lifecycle

```text
REGISTERED
    |
    v
VALIDATED
    |
    v
ENABLED
    |
    v
EXECUTING
    |
    +--> COMPLETED
    +--> FAILED
    +--> CANCELLED
    +--> TIMEOUT
    +--> POLICY_DENIED
    +--> RESOURCE_EXHAUSTED
```

Only validated and enabled agents may be executed.

---

## 12. Agent Execution Loop

```text
1. Receive request
2. Resolve agent
3. Load immutable agent version
4. Authorize user -> agent
5. Load execution policy
6. Build ContextPackage
7. Invoke Model Gateway
8. Inspect model response
9. If final answer -> finish
10. If tool request -> validate and authorize
11. Execute tool
12. Add result to context
13. Continue within limits
14. Persist execution result
15. Emit audit/observability events
```

The Agent Harness, not the model, controls the loop.

---

## 13. Stop Conditions

Execution must stop when:

- the model produces a valid final response
- maximum steps are reached
- timeout occurs
- user cancellation is received
- policy denies continuation
- required capability is unavailable
- resource limits are exceeded
- an unrecoverable tool/workflow error occurs

The system must not continue indefinitely because a model repeatedly requests actions.

---

## 14. Output Contract

Agents may define structured output requirements.

Examples:

```text
answer
sources
confidence
actions_taken
warnings
```

For machine-consumed workflows, JSON/schema-constrained output should be preferred where supported by the Model Gateway.

Invalid structured output must be rejected or repaired through a bounded mechanism rather than silently accepted.

---

## 15. Security Model

Effective permissions are the intersection of:

```text
User permissions
AND
Agent permissions
AND
Tool/workflow permissions
AND
Resource permissions
AND
Platform security policy
```

An agent definition cannot grant permissions that the platform does not allow.

---

## 16. Observability

Every execution should expose:

- execution ID
- agent ID
- agent version
- user/session reference
- start/end time
- model used
- context sources
- tool calls
- workflow calls
- token usage where available
- final status
- failure reason

Sensitive prompts, documents, and secrets must not be logged by default.

---

## 17. Design Constraints

The following are prohibited:

```text
Agent -> direct database access
Agent -> direct shell access
Agent -> direct filesystem access
Agent -> direct network access
Agent -> direct model-provider API
```

Required pattern:

```text
Agent
  -> Agent Harness
  -> approved subsystem
  -> controlled capability
```

---

## 18. Acceptance Criteria

The Agent Design is complete when:

- agents are versioned
- execution is controlled by the Agent Harness
- model providers are abstracted
- context is assembled by the Context Engine
- memory access is explicit
- tools/workflows are permission controlled
- execution is bounded
- lifecycle state is persisted
- executions are auditable
- failures terminate safely
