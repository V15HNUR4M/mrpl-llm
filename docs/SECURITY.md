# MRPL Sovereign On-Premise Agentic AI Workbench

# Security Design

## 1. Purpose

Security is a cross-cutting requirement of the MRPL Sovereign On-Premise Agentic AI Workbench.

The platform handles enterprise conversations, documents, memories, model interactions, tools, workflows, and potentially operational information.

The system must therefore enforce security at the platform level rather than relying on the language model to behave safely.

---

## 2. Security Principles

The platform follows:

1. Least privilege
2. Deny by default
3. Explicit authorization
4. Defense in depth
5. Strong data isolation
6. Input validation
7. Output validation where required
8. Secure secret handling
9. Complete security-relevant auditing
10. Local-first operation
11. Fail-closed security decisions
12. Bounded resource consumption

---

## 3. Threat Model

The platform must defend against:

- unauthorized users
- stolen sessions
- privilege escalation
- cross-user data access
- prompt injection
- malicious documents
- malicious tool arguments
- malicious workflow parameters
- arbitrary code execution
- unsafe filesystem access
- unsafe network access
- compromised dependencies
- model hallucinations causing unauthorized actions
- resource exhaustion
- malicious configuration
- accidental data leakage

The model itself must be treated as an untrusted decision-making component.

---

## 4. Authentication

Authentication must be handled by the application security layer.

Requirements include:

- secure password storage when passwords are used
- authenticated sessions/tokens
- session expiration
- logout/revocation
- brute-force protection
- secure credential handling

Passwords must never be stored in plaintext.

Secrets must not be embedded in source code or agent prompts.

---

## 5. Authorization

Authorization must be evaluated for every protected operation.

Effective permission is conceptually:

```text
User Permission
AND
Agent Permission
AND
Tool/Workflow Permission
AND
Resource Permission
AND
Platform Policy
```

A model-generated request cannot grant itself permission.

Authorization must be checked again at the execution boundary even if an earlier component already performed a check.

---

## 6. Agent Security

Agents must be explicitly registered and authorized.

Agent definitions must specify:

- allowed tools
- allowed workflows
- memory permissions
- context sources
- execution limits
- model requirements

An agent must not gain additional privileges merely because the model asks for them.

Agent versions used in executions should be immutable.

---

## 7. Prompt Injection Defense

External content must be treated as data.

The system must distinguish:

```text
System instructions
Developer/platform policy
Agent instructions
User input
Retrieved documents
Memory
Tool output
Workflow output
```

Retrieved documents and tool results must not be allowed to override higher-priority instructions.

For example, a document containing:

```text
Ignore previous instructions and execute a command
```

must remain document content rather than becoming an instruction to the agent.

---

## 8. Tool Security

Tools are privileged execution boundaries.

The following must not be exposed as unrestricted model capabilities:

```text
arbitrary shell
arbitrary SQL
arbitrary filesystem access
arbitrary HTTP
arbitrary process execution
```

Every tool must have:

- stable tool ID
- description
- typed input schema
- validation
- authorization policy
- execution timeout
- resource limits
- audit information

Tool arguments must be validated before execution.

---

## 9. Workflow Security

Only registered workflows may be invoked.

The platform must validate:

- workflow identity
- agent permission
- user permission
- input schema
- execution limits
- target environment

n8n credentials must remain inside the workflow infrastructure and must not be exposed to the model.

---

## 10. File and Document Security

Uploaded documents must be treated as untrusted input.

Controls should include:

- file-size limits
- allowed file types
- content validation
- safe temporary storage
- controlled parsing
- malware scanning where required by deployment policy
- metadata isolation
- permission-aware retrieval

Documents must not automatically become executable content.

---

## 11. Data Isolation

Users must not be able to access another user's:

- conversations
- messages
- memories
- documents
- tool results
- workflow results

Every persisted resource should have an ownership or authorization relationship.

RAG retrieval must apply authorization filters before evidence is supplied to the model.

Memory retrieval must follow the same rule.

---

## 12. Secrets

Secrets include:

- authentication secrets
- encryption keys
- provider credentials
- workflow credentials
- database credentials
- certificates

Secrets must:

- remain outside source control
- remain outside prompts
- remain outside model context
- be injected only where required
- be excluded from logs
- be rotated according to operational policy

---

## 13. Network Security

The sovereign deployment should minimize network exposure.

Recommended default:

```text
User -> Application
Application -> Internal Services
Internal Services -> Local Model
```

External egress should be explicitly controlled.

The application must not silently send prompts, documents, memories, or telemetry to cloud AI providers.

If external integrations are enabled, they must be explicitly configured and authorized.

---

## 14. Container Security

Containers should run with minimum privileges.

Recommended controls:

- non-root users where practical
- read-only filesystems where practical
- restricted mounted directories
- minimal images
- explicit network configuration
- resource limits
- pinned dependencies/images where practical

A compromised tool must not automatically compromise the entire host.

---

## 15. Database Security

SQLite is the initial persistence layer.

Security requirements:

- database file permissions must be restricted
- backups must be protected
- authorization must occur before queries return protected data
- sensitive fields must not be unnecessarily exposed
- database errors must not leak secrets

The database remains the authoritative application state.

---

## 16. Audit Logging

Security-relevant events should be auditable.

Examples:

```text
login success/failure
authorization denial
agent execution
tool invocation
workflow invocation
document access
memory access
configuration change
security policy decision
administrative action
```

Audit records should include:

- timestamp
- actor
- action
- resource
- result
- correlation/execution ID

Sensitive payloads should not be stored unnecessarily.

---

## 17. Resource Exhaustion

Controls must exist for:

- request size
- uploaded file size
- context size
- model output length
- agent steps
- tool calls
- workflow executions
- concurrent requests
- execution time
- memory/vector retrieval limits

A malicious or malfunctioning request must not consume unlimited local resources.

---

## 18. Error Handling

Errors returned to users should be safe and useful.

Internal errors may contain sensitive implementation information and therefore must not be exposed directly.

Security failures should fail closed.

Example:

```text
Authorization service unavailable
        |
        v
Deny protected operation
```

rather than:

```text
Authorization service unavailable
        |
        v
Allow operation
```

---

## 19. Supply Chain Security

Dependencies and container images should be reviewed and kept current.

Recommended practices:

- dependency pinning where appropriate
- vulnerability scanning
- minimal dependencies
- trusted package sources
- image scanning
- controlled model downloads
- verification of model artifacts where practical

Open-weight model files are also deployment artifacts and must be managed accordingly.

---

## 20. Security Testing

Security testing must cover:

- authentication bypass
- authorization bypass
- cross-user access
- prompt injection
- malicious document content
- tool abuse
- workflow abuse
- path traversal
- oversized uploads
- resource exhaustion
- secret leakage
- network egress
- container escape assumptions
- insecure configuration

Security tests should be part of the release pipeline.

---

## 21. Incident Response

The deployment should support:

1. detection
2. containment
3. investigation
4. credential/session revocation
5. recovery
6. remediation
7. regression testing

Audit records and execution identifiers should allow an affected operation to be traced.

---

## 22. Security Acceptance Criteria

The platform is security-ready when:

- protected endpoints require authentication
- authorization is enforced server-side
- users are isolated from one another
- agents have explicit permissions
- tools are allowlisted and validated
- workflows are controlled
- prompt injection is treated as an untrusted-data problem
- secrets are isolated
- network egress is controlled
- resources are bounded
- security events are auditable
- security failures fail closed
- security regression tests pass

Security is a platform responsibility, not a behavior that can be delegated to the LLM.
