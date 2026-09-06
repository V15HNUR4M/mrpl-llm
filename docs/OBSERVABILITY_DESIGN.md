# MRPL Sovereign On-Premise Agentic AI Workbench

# Observability Design

## 1. Purpose

This document defines how the MRPL AI Workbench exposes operational behavior through logs, metrics, traces, health information, and audit records.

Observability must make it possible to answer:

- Is the system healthy?
- Why is a request slow?
- Which model handled a request?
- Which agent executed?
- Which context sources were used?
- Which tools were invoked?
- Why did an agent stop?
- Where did an error occur?
- Is the model overloaded?
- Is RAG retrieval degrading?
- Is memory persistence working?
- Is a security policy blocking activity?

Observability must not compromise sovereignty or expose sensitive enterprise information unnecessarily.

---

# 2. Observability Principles

1. **Local-first** — telemetry remains inside the deployment unless explicitly exported.
2. **Correlation-first** — every meaningful operation has correlation identifiers.
3. **Structured data** — logs should be machine-readable.
4. **Minimal sensitive content** — prompts and documents are not logged by default.
5. **Layered visibility** — health, metrics, logs, traces, and audit serve different purposes.
6. **Actionable telemetry** — measurements should correspond to operational decisions.
7. **Low overhead** — instrumentation must not materially degrade inference.
8. **Failure visibility** — errors must retain enough context to diagnose them.
9. **Retention control** — telemetry has explicit retention periods.
10. **Tenant/session isolation** — telemetry must respect authorization boundaries.

---

# 3. Observability Layers

```text
                 +----------------------+
                 |     Dashboards       |
                 +----------+-----------+
                            |
                 +----------+-----------+
                 | Metrics / Logs /     |
                 | Traces / Alerts      |
                 +----------+-----------+
                            |
          +-----------------+------------------+
          |                 |                  |
       API Layer       Agent Runtime      Model Gateway
          |                 |                  |
          +-----------------+------------------+
                            |
                 RAG / Memory / Tools
                            |
                     Persistence
```

The observability stack is separate from business logic.

---

# 4. Health Model

Health is divided into:

## 4.1 Liveness

Answers:

> Is the process alive?

A liveness failure normally indicates the service should be restarted.

## 4.2 Readiness

Answers:

> Can the service accept work?

Readiness may fail when:

- database is unavailable
- model is not loaded
- required storage is unavailable
- required dependency is unhealthy

## 4.3 Dependency Health

Reports the state of dependencies individually.

Example:

```json
{
  "database": "healthy",
  "vector_store": "healthy",
  "model_gateway": "healthy",
  "inference": "healthy",
  "memory": "degraded"
}
```

---

# 5. Correlation IDs

Every inbound request should receive:

- `request_id`
- `trace_id`
- `session_id` when applicable
- `conversation_id` when applicable
- `agent_execution_id` when applicable

Tool executions should additionally have:

- `tool_execution_id`

Workflow executions should have:

- `workflow_execution_id`

Identifiers must not contain user-sensitive information.

---

# 6. Structured Logging

Logs should be emitted as structured records.

Example:

```json
{
  "timestamp": "2026-09-05T12:00:00Z",
  "level": "INFO",
  "service": "agent-harness",
  "event": "agent_execution_completed",
  "request_id": "...",
  "trace_id": "...",
  "agent_id": "...",
  "agent_version": "...",
  "duration_ms": 1834,
  "status": "success"
}
```

Application logs must not rely exclusively on free-form strings.

---

# 7. Log Levels

## DEBUG

Detailed developer diagnostics.

Must normally be disabled in production.

## INFO

Normal lifecycle events.

Examples:

- request accepted
- agent started
- retrieval completed
- model selected
- execution completed

## WARN

Recoverable or suspicious conditions.

Examples:

- fallback model selected
- retrieval returned low-confidence results
- queue delay exceeded target
- optional dependency unavailable

## ERROR

Failed operation requiring investigation.

## CRITICAL

Service-wide or data-integrity-impacting failure.

---

# 8. Sensitive Data Policy

The following must not be logged by default:

- passwords
- access tokens
- API keys
- session secrets
- full user prompts
- full model responses
- raw uploaded documents
- confidential document content
- tool credentials
- personally sensitive information

Where debugging requires payload capture, it must be explicitly enabled, access-controlled, time-limited, and subject to organizational policy.

---

# 9. Core Metrics

## API

- request count
- request rate
- response latency
- error rate
- active requests
- HTTP status distribution

## Agent

- executions started
- executions completed
- executions failed
- execution duration
- cancellation count
- maximum step count reached
- tool calls per execution

## Model Gateway

- model requests
- model request latency
- tokens in
- tokens out
- tokens/sec where available
- queue depth
- fallback count
- model errors
- context overflow count

## RAG

- documents ingested
- ingestion failures
- retrieval count
- retrieval latency
- chunks returned
- low-confidence retrieval count
- embedding failures

## Memory

- reads
- writes
- summarizations
- extraction failures
- storage latency
- memory size

## Tools

- tool calls
- authorization denials
- validation failures
- execution failures
- execution latency

## Workflow

- executions
- success rate
- failure rate
- queue time
- execution duration

---

# 10. Model Performance Metrics

Model observability should separate:

### Infrastructure performance

- CPU utilization
- RAM
- VRAM
- GPU utilization
- GPU temperature
- disk I/O
- network I/O

### Inference performance

- time to first token
- total generation time
- prompt processing time
- generation throughput
- queue wait
- batch size where supported

### Quality indicators

Quality is measured primarily through the Evaluation framework rather than raw infrastructure metrics.

---

# 11. Agent Execution Trace

A trace should represent:

```text
Request
 └── Agent execution
      ├── Context construction
      │    ├── Memory retrieval
      │    └── RAG retrieval
      ├── Model request
      ├── Tool decision
      │    └── Tool execution
      ├── Model request
      └── Final response
```

This allows operators to determine which stage caused latency or failure.

---

# 12. RAG Observability

Each retrieval operation should expose metadata such as:

- retrieval strategy
- query identifier
- collection/index
- number of candidates
- number returned
- retrieval latency
- reranking latency
- confidence/relevance statistics

Raw retrieved text should not be included in operational logs by default.

---

# 13. Memory Observability

Track:

```text
conversation read
conversation write
summary generated
memory candidate extracted
memory accepted
memory rejected
memory retrieval
memory deletion
```

The system should expose counts and latency rather than confidential memory contents.

---

# 14. Tool Observability

Every tool execution should be traceable.

Required metadata:

- tool ID
- tool version
- agent ID
- authorization decision
- validation result
- start/end time
- duration
- final status
- error category

Do not log tool credentials or unrestricted tool payloads.

---

# 15. Security Observability

Security-relevant events include:

- login success/failure
- logout
- session expiration
- permission denial
- policy denial
- blocked tool execution
- invalid file upload
- suspicious request pattern
- administrative configuration change
- model registration
- workflow registration
- agent registration

These events belong in the audit subsystem as well as appropriate operational logs.

---

# 16. Audit vs Logs

Operational logs answer:

> What happened technically?

Audit records answer:

> What security-relevant action happened, by whom, and under what authority?

They must remain conceptually separate.

Audit events should be durable and tamper-evident according to organizational requirements.

---

# 17. Tracing

Distributed tracing should be supported even if the first deployment uses a single node.

Recommended trace boundaries:

```text
HTTP request
   ↓
Agent execution
   ↓
Context engine
   ↓
RAG / Memory
   ↓
Model gateway
   ↓
Inference
```

Trace propagation should use standard correlation mechanisms.

---

# 18. Dashboards

A minimum operational dashboard should contain:

### System

- service health
- CPU
- RAM
- GPU
- disk
- uptime

### API

- requests/minute
- p50/p95/p99 latency
- errors

### Agent

- active executions
- completion rate
- average duration
- tool-call rate

### Model

- active model
- queue depth
- tokens/sec
- latency
- failures

### RAG

- ingestion status
- retrieval latency
- retrieval failures

---

# 19. Alerts

Initial alerts:

| Alert | Condition |
|---|---|
| API unhealthy | readiness failure |
| Model unavailable | no healthy configured model |
| High latency | sustained p95 above target |
| High error rate | sustained error percentage |
| Disk critical | free space below threshold |
| GPU memory pressure | sustained near-capacity usage |
| Queue saturation | queue exceeds configured limit |
| Database failure | persistence unavailable |
| Repeated auth failures | threshold exceeded |
| Tool denial spike | abnormal policy-denial rate |

Thresholds must be environment-specific.

---

# 20. Retention

Telemetry retention should be configurable.

Example prototype policy:

```text
Debug logs: short retention
Application logs: 7–30 days
Metrics: 30–90 days
Traces: short retention
Audit records: according to MRPL policy
```

Long-term audit retention must follow enterprise requirements.

---

# 21. Offline Observability

The platform must remain observable without cloud telemetry.

A fully local deployment can use:

- local log files
- local metrics storage
- local dashboards
- local trace storage

No telemetry should silently leave the MRPL network.

---

# 22. Failure Diagnosis Workflow

When a request fails:

```text
1. Find request_id
2. Inspect API log
3. Follow trace_id
4. Inspect agent execution
5. Inspect context construction
6. Inspect model gateway
7. Inspect inference runtime
8. Inspect RAG/memory/tool spans
9. Inspect audit events if security-related
10. Reproduce with the same configuration
```

---

# 23. Observability Acceptance Criteria

Observability is complete when operators can:

- identify unhealthy services
- correlate one request across services
- identify slow stages
- identify model failures
- identify RAG failures
- identify memory failures
- identify tool failures
- identify security denials
- inspect resource usage
- diagnose deployment failures
- operate without external telemetry services

---

# 24. Privacy and Sovereignty Requirement

Observability must never become a hidden data-exfiltration channel.

Telemetry exporters must be explicitly configured.

The default deployment should export to local destinations only.

---

# 25. Implementation Guidance

Instrumentation should be implemented behind small reusable interfaces so the core business logic does not depend on a specific monitoring vendor.

Example conceptual interfaces:

```text
Logger
MetricsRecorder
Tracer
AuditRecorder
HealthReporter
```

This keeps the platform provider-independent and allows lightweight prototype observability to evolve into an enterprise stack without rewriting the application.
