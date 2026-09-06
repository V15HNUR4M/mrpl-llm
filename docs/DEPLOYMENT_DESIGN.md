# MRPL Sovereign On-Premise Agentic AI Workbench

# Deployment Design

## 1. Purpose

This document defines the deployment architecture for the MRPL Sovereign On-Premise Agentic AI Workbench.

The deployment must preserve the core platform properties:

- on-premise execution
- local model inference
- no mandatory cloud dependency
- controlled network egress
- reproducible deployment
- persistent local storage
- horizontal separation of services where required
- operational simplicity for an enterprise environment
- secure upgrades and rollback

Deployment is an implementation concern. It must not change the logical contracts defined by the Agent Harness, Context Engine, Model Gateway, RAG, Memory, Tool/MCP, Workflow, API, Security, and Data Model documents.

---

# 2. Deployment Principles

The platform follows these principles:

1. **Local-first** — normal inference and knowledge operations execute inside the MRPL environment.
2. **Sovereign-by-default** — external APIs are not required for normal operation.
3. **Service isolation** — major runtime responsibilities are independently deployable.
4. **Persistent state separation** — application containers remain disposable; databases and model assets are persistent.
5. **Least privilege** — each service receives only the filesystem, network, and credentials it requires.
6. **Deterministic configuration** — deployment configuration is explicit and version-controlled.
7. **Observability by default** — health, metrics, logs, and traces are part of deployment rather than an afterthought.
8. **Graceful degradation** — failure of an optional subsystem must not silently compromise security or data integrity.
9. **Upgrade safety** — schema, model, and application upgrades must be reversible where practical.
10. **Hardware-aware inference** — GPU/CPU allocation is explicit and measurable.

---

# 3. Deployment Topology

A reference deployment is:

```text
                    MRPL Internal Network
                           |
                    +------+------+
                    | Reverse     |
                    | Proxy       |
                    +------+------+
                           |
                    +------+------+
                    | API /       |
                    | Application |
                    +------+------+
                       /   |    \
                      /    |     \
                     /     |      \
              +-----+  +---+---+  +------+
              |Agent|  |RAG/   |  |Memory|
              |Harness|Context|  |Store |
              +--+--+  +---+---+  +------+
                 |          |          |
                 |          |          |
              +--+----------+----------+--+
              |        Persistence       |
              | SQLite / Vector Store    |
              +---------------------------+
                 |
          +------+------+
          | Model       |
          | Gateway     |
          +------+------+
                 |
       +---------+----------+
       | Local Inference    |
       | Runtime            |
       | CPU / NVIDIA GPU   |
       +--------------------+

 Optional:
   MCP/Tool services
   n8n workflow engine
   observability stack
   document/object storage
```

The exact process boundaries may change between prototype and production, but the logical boundaries must remain intact.

---

# 4. Deployment Profiles

## 4.1 Development

Recommended characteristics:

- Docker Compose
- one host
- local SQLite
- local vector database
- local model runtime
- development logging
- hot reload where useful
- relaxed resource limits

The development profile must still enforce the same API contracts and security boundaries as production.

## 4.2 Demonstration / SIH Prototype

The prototype should prioritize:

- reliable startup
- predictable inference
- simple recovery
- clear UI
- visible agent/RAG/tool behavior
- local-only operation
- reproducible demo data

A single workstation can host the complete stack.

## 4.3 Production Single Node

A production single-node deployment may run:

- reverse proxy
- backend API
- agent runtime
- RAG services
- memory services
- model gateway
- inference runtime
- persistence
- observability

using isolated containers.

Persistent directories must be mounted outside disposable containers.

## 4.4 Production Multi-Node

For larger installations:

```text
Node A: API + Agent services
Node B: GPU inference
Node C: Persistence / vector storage
Node D: Observability
```

The Model Gateway abstracts the inference node from the application layer.

---

# 5. Container Boundaries

A reference container layout is:

| Container | Responsibility | Persistent data |
|---|---|---|
| `mrpl-api` | HTTP API and orchestration entry point | No |
| `mrpl-agent` | Agent execution | No |
| `mrpl-model-gateway` | Model/provider abstraction | Optional cache |
| `mrpl-inference` | Local LLM inference | Model files |
| `mrpl-rag` | Document ingestion/retrieval | Documents/indexes |
| `mrpl-memory` | Conversation/semantic memory | Database |
| `mrpl-vector` | Vector search | Vector data |
| `mrpl-n8n` | Workflow execution | Workflow state |
| `mrpl-proxy` | TLS/reverse proxy | Certificates |
| `mrpl-observability` | Metrics/logging/tracing | Retention data |

A prototype may combine some services into fewer containers, but the interfaces should remain compatible with the logical architecture.

---

# 6. Docker Compose Strategy

Docker Compose is the reference deployment mechanism for development and small installations.

The Compose file should:

- define explicit service names
- define health checks
- define persistent volumes
- define internal networks
- avoid hard-coded secrets
- expose only required ports
- define restart policies
- support CPU/GPU configuration
- use pinned image versions where practical

The obsolete Compose `version` field should not be used.

---

# 7. Networks

At minimum:

```text
frontend-network
       |
application-network
       |
data-network
       |
inference-network
```

Not every service should join every network.

Recommended access:

| Service | API | Data | Inference |
|---|---:|---:|---:|
| Proxy | Yes | No | No |
| API | Yes | Yes | Yes |
| Agent | Internal | Yes | Through gateway |
| RAG | Internal | Yes | No |
| Memory | Internal | Yes | No |
| Model Gateway | Internal | No | Yes |
| Inference | Gateway only | Model volume | N/A |

External internet access should be disabled for services that do not require it.

---

# 8. Persistent Storage

Persistent storage must be separated from container lifecycles.

Suggested layout:

```text
data/
├── sqlite/
├── documents/
├── vector/
├── memory/
├── models/
├── uploads/
├── audit/
├── backups/
└── exports/
```

The application must never treat a container filesystem as authoritative persistent storage.

---

# 9. Model Deployment

Model artifacts are infrastructure assets.

Each installed model should have:

- model identifier
- provider/runtime identifier
- quantization
- context limit
- supported modalities
- checksum
- storage location
- version
- hardware requirements
- capability metadata

Example:

```text
models/
└── qwen/
    └── <model-version>/
        ├── model files
        ├── manifest.json
        └── checksum
```

The Model Gateway must select models using capability metadata rather than hard-coded model names throughout application code.

---

# 10. GPU Deployment

When NVIDIA GPUs are available, the inference container may receive GPU access.

Requirements:

- host NVIDIA driver installed
- compatible container runtime
- explicit GPU allocation
- measured VRAM usage
- model-specific memory limits

The application must remain functional in CPU mode where the selected model supports it, although performance may be reduced.

The system must not assume that every deployment has the same GPU.

---

# 11. Configuration

Configuration hierarchy:

```text
Defaults
   ↓
Environment variables
   ↓
Deployment configuration
   ↓
Runtime-safe overrides
```

Secrets must never be committed to source control.

Typical configuration categories:

```text
APP_
DB_
RAG_
MEMORY_
MODEL_
INFERENCE_
MCP_
WORKFLOW_
SECURITY_
OBSERVABILITY_
```

Configuration should be validated during startup.

---

# 12. Secrets

Secrets may include:

- session signing keys
- database credentials where applicable
- internal service credentials
- TLS private keys
- workflow credentials

Secrets must be injected through:

- environment secrets
- mounted secret files
- an approved enterprise secret manager

They must not be embedded in Docker images or committed `.env` files.

---

# 13. Health Checks

Every long-running service should expose an appropriate health check.

Health states:

```text
STARTING
HEALTHY
DEGRADED
UNHEALTHY
```

Health checks should distinguish:

- process is alive
- service is ready
- dependencies are available
- model is loaded
- storage is writable

A model-loading failure must not be reported as a healthy inference service.

---

# 14. Startup Order

Logical startup:

```text
Infrastructure
      ↓
Persistence
      ↓
Vector / storage
      ↓
Model runtime
      ↓
Model Gateway
      ↓
RAG / Memory
      ↓
Agent services
      ↓
API
      ↓
Reverse proxy
```

Container startup order alone is insufficient. Services must wait for readiness, not merely process creation.

---

# 15. Graceful Shutdown

Services must:

1. stop accepting new work
2. allow active requests to finish where possible
3. persist required state
4. close database connections
5. flush logs
6. terminate workers
7. exit cleanly

Long-running agent executions must have cancellation semantics.

---

# 16. Backup Strategy

Backups must cover:

- SQLite/database state
- vector indexes
- uploaded documents
- memory records
- configuration
- audit logs
- workflow definitions
- model manifests

Large model binaries may be backed up separately because they can be reconstructed from controlled artifacts.

At minimum:

```text
Daily:
  application state

Weekly:
  full persistent data

Before upgrade:
  database + configuration + workflow state
```

Backups must be encrypted where organizational policy requires it.

---

# 17. Restore Strategy

A restore procedure must be tested, not merely documented.

Order:

```text
Restore configuration
       ↓
Restore database
       ↓
Restore documents
       ↓
Restore vector indexes
       ↓
Restore memory
       ↓
Install/verify model artifacts
       ↓
Start services
       ↓
Run health checks
       ↓
Run smoke tests
```

A deployment is not considered recoverable until restoration has been validated.

---

# 18. Upgrade Strategy

Application upgrades should follow:

```text
Backup
  ↓
Validate release
  ↓
Deploy new images
  ↓
Run migrations
  ↓
Run health checks
  ↓
Run smoke tests
  ↓
Enable traffic
```

If validation fails:

```text
Stop
 ↓
Restore previous application version
 ↓
Restore data if migration is reversible
 ↓
Verify
```

Database migrations must be versioned and preferably backward-compatible across one release boundary.

---

# 19. Model Upgrade Strategy

Model upgrades are independent of application releases.

A new model must be:

1. downloaded/imported through an approved process
2. checksum-verified
3. registered
4. capability-tested
5. benchmarked
6. evaluated against regression datasets
7. assigned an explicit version
8. activated through configuration

The previous model should remain available until the new model passes validation.

---

# 20. Deployment Security

Production deployment must:

- minimize exposed ports
- use TLS for user-facing traffic
- isolate internal services
- apply least-privilege filesystem permissions
- disable unnecessary container capabilities
- avoid privileged containers
- restrict outbound network access
- validate uploaded files
- rotate credentials
- retain audit logs

---

# 21. Resource Management

CPU, RAM, VRAM, disk, and concurrency must be monitored.

The platform should enforce:

- maximum upload size
- maximum document size
- maximum concurrent inference requests
- maximum agent execution time
- maximum tool execution time
- maximum workflow execution time
- maximum context budget

Resource exhaustion must produce controlled errors rather than host instability.

---

# 22. Scaling

The first scaling target should normally be inference.

Possible architecture:

```text
             API
              |
        Model Gateway
        /     |      \
     GPU-1  GPU-2   GPU-3
```

The gateway can route requests based on:

- model capability
- availability
- queue depth
- context requirement
- modality
- latency target

Stateful data should remain external to stateless application containers.

---

# 23. Disaster Recovery

The deployment must define:

- Recovery Point Objective (RPO)
- Recovery Time Objective (RTO)
- backup retention
- restore owner
- failure scenarios
- recovery procedure

Example initial targets for a prototype:

```text
RPO: 24 hours
RTO: 4 hours
```

Production values must be determined by MRPL operational requirements.

---

# 24. Deployment Verification

After deployment:

```text
1. Check container status
2. Check health endpoints
3. Authenticate
4. Create conversation
5. Send normal prompt
6. Execute RAG query
7. Upload test document
8. Verify retrieval
9. Verify memory persistence
10. Verify tool authorization
11. Verify audit logging
12. Verify model capability
13. Verify observability
```

A deployment is successful only when functional and security smoke tests pass.

---

# 25. Deployment Acceptance Criteria

A release is deployable when:

- all required services start successfully
- health checks pass
- persistent storage is writable
- the configured model is available
- authentication works
- inference works
- RAG works
- memory works
- tool controls work
- audit logging works
- metrics/logging are available
- no mandatory cloud dependency exists
- backup and rollback procedures are known

---

# 26. Reference Prototype Command Flow

```text
docker compose build
docker compose up -d
docker compose ps
docker compose logs
```

Then execute application smoke tests.

The exact commands may evolve with the repository implementation, but deployment documentation must always reflect the actual Compose configuration shipped with the project.
