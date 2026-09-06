# MRPL Sovereign On-Premise Agentic AI Workbench
## Track 13 — Production Deployment & Operations Guide

This guide details the complete, reproducible, sovereign on-premise deployment of the MRPL Agentic AI Workbench.

---

## 1. Sovereignty Guarantee & Architecture

### Sovereignty Specification
The MRPL AI Workbench operates entirely on-premise without relying on external cloud APIs.

- **Normal Application Runtime**: Normal application operation does **not** require external LLM APIs (OpenAI, Anthropic, Gemini, Groq), external embedding APIs, cloud vector databases (Pinecone, Weaviate Cloud), cloud storage (AWS S3, GCS), or external authentication services (Auth0, Okta).
- **Network Boundaries**: All inference is routed through the local Ollama daemon on the sovereign network. Data persistence (relational, vector, attachments) resides strictly within local volumes.
- **Build/Provisioning vs Runtime**: Build time requires standard container image pulls and package installation (pip, npm) unless pre-staged via local offline tarballs. Model weights are pulled once during initial provisioning or loaded from local `.ollama` volume caches.

### System Topology
```
[ Browser / Client ]
         │ (HTTP:3000)
         ▼
[ mrpl_frontend (Nginx 1.27-alpine) ]
   ├── Serves SPA Static Assets
   ├── Reverse Proxies /api/v1/ ────┐
   └── Reverse Proxies /health/ ───┐│
                                   ││ (HTTP:8000)
                                   ▼▼
[ mrpl_backend (FastAPI / Python 3.11-slim) ]
   ├── Agent Harness & Context Engine
   ├── Local Tool Executor & Auth Policy
   ├── Chroma Vector Store ───► [ Persistent Volume: mrpl_data ]
   ├── SQLite DB (mrpl.db) ───► [ Persistent Volume: mrpl_data ]
   └── Model Gateway
         │ (HTTP:11434)
         ▼
[ mrpl_ollama (Ollama 0.33.3 / Pinned Runtime) ]
   ├── Chat Model: llama3.2:latest
   ├── Embedding Model: nomic-embed-text
   └── Model Weights Storage ──► [ Persistent Volume: mrpl_ollama_data ]
```

---

## 2. Hardware & System Prerequisites

### Minimum Hardware Requirements
- **CPU**: 4 physical cores (x86_64 / ARM64)
- **RAM**: 16 GB system memory (minimum 8 GB dedicated to Docker)
- **Storage**: 30 GB available SSD space (for OS, Docker images, vector store, and model weights)
- **GPU (Optional / Recommended)**: NVIDIA GPU with CUDA support for low-latency inference (e.g. RTX 3060+ or Tesla T4/A10 with 8GB+ VRAM).

### Software Prerequisites & Component Versions Matrix
The sovereign deployment has been verified against the following pinned component versions:

| Component | Pinned Version | Base / Image |
| :--- | :--- | :--- |
| **Backend Runtime** | Python 3.11.9 | `python:3.11-slim` |
| **Frontend Runtime** | Node.js 20.x Alpine (Build) / Nginx 1.27-alpine (Serving) | `nginx:1.27-alpine` |
| **Local LLM Engine** | Ollama 0.33.3 | `ollama/ollama:0.33.3` (or digest `sha256:32931b46719f...`) |
| **Relational Database** | SQLite 3 / aiosqlite 0.20.0 | Built-in / In-volume |
| **Vector Database** | ChromaDB 0.4.22+ | In-process persistent storage |
| **Container Engine** | Docker 24.0+ (Tested 29.7.2) | Docker Compose v2.20+ |

---

## 3. Environment Configuration

Copy the production environment template:
```bash
cp .env.example .env
```

### Key Environment Variables (`.env`)
| Variable | Description | Production Requirement |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Deployment environment mode | Must be set to `production` |
| `SECRET_KEY` | Cryptographic key for JWT tokens | Must be >= 32 characters, non-default |
| `FIRST_SUPERUSER` | Initial administrative username | Defaults to `admin` |
| `FIRST_SUPERUSER_PASSWORD` | Initial administrative password | Must be >= 10 characters, non-default |
| `OLLAMA_BASE_URL` | Local Ollama API endpoint | `http://ollama:11434` (container network) |
| `DEFAULT_CHAT_MODEL` | Primary local chat model | `llama3.2:latest` |
| `DEFAULT_EMBEDDING_MODEL`| Primary embedding model | `nomic-embed-text` |
| `SQLITE_URL` | Async SQLite database URI | `sqlite+aiosqlite:////app/data/mrpl.db` |
| `ENABLE_OPENAPI` | Swagger/OpenAPI documentation | `false` in production |
| `ENABLE_TEST_ENDPOINTS` | Debug/test background endpoints | `false` in production |

> [!CAUTION]
> In `ENVIRONMENT=production`, the application will **fail fast** at startup if `SECRET_KEY` is missing, less than 32 characters, or contains known test strings (such as `test-secret-key-12345`).

---

## 4. Model Provisioning

Before starting the full application stack, ensure required models are provisioned into the `mrpl_ollama_data` volume:

```bash
# 1. Start Ollama service only
docker compose up -d ollama

# 2. Pull verified chat model
docker compose exec ollama ollama pull llama3.2:latest

# 3. Pull verified embedding model
docker compose exec ollama ollama pull nomic-embed-text

# 4. Verify installed models
docker compose exec ollama ollama list
```

---

## 5. Startup & Operations

### Build and Launch the Stack
```bash
# Build production images and start all containers in detached mode
docker compose up --build -d
```

### Monitor Service Startup and Readiness
```bash
# View aggregated logs
docker compose logs -f

# Check container health status
docker compose ps
```

Expected container status:
```text
NAME            IMAGE                      STATUS                    PORTS
mrpl_ollama     ollama/ollama:0.33.3       Up (healthy)              0.0.0.0:11434->11434/tcp
mrpl_backend    mrpl-llm-backend           Up (healthy)              0.0.0.0:8000->8000/tcp
mrpl_frontend   mrpl-llm-frontend          Up (healthy)              0.0.0.0:3000->80/tcp
```

### Accessing the Application
- **Frontend UI**: Open `http://localhost:3000` in a browser.
- **Backend API**: Accessible via `http://localhost:3000/api/v1` (reverse-proxied) or `http://localhost:8000/api/v1` (direct).

---

## 6. Health & Readiness Probes

The application provides distinct probes for orchestration:

### Liveness Probe (`GET /health/live`)
- Verifies process execution and event loop responsiveness.
- Returns `HTTP 200 {"status": "alive"}`.
- Does **not** fail if Ollama is temporarily busy or downloading, preventing container crash loops.

### Readiness Probe (`GET /health/ready`)
- Deep dependency check validating:
  1. **SQLite Database**: Executes `SELECT 1`.
  2. **Chroma Vector Store**: Tests read access and counts indexed chunks.
  3. **Ollama Reachability**: Confirms HTTP connection to Ollama daemon.
  4. **Model Availability**: Confirms `llama3.2:latest` and `nomic-embed-text` are installed.
  5. **Storage Paths**: Confirms write permissions for uploads and attachments.
- Returns `HTTP 200 {"status": "ready", ...}` when all dependencies are ready.
- Returns `HTTP 503 {"status": "not_ready", ...}` if any critical dependency is missing.

---

## 7. Persistent Volumes & Data Layout

Application state is isolated in two named Docker volumes:
1. `mrpl_data`:
   - `/app/data/mrpl.db`: SQLite database (users, conversations, messages, workflows, telemetry).
   - `/app/data/chroma/`: Vector index for RAG document retrieval.
   - `/app/data/uploads/`: Original uploaded document files.
   - `/app/data/attachments/`: Multimodal attachments (images, PDFs).
2. `mrpl_ollama_data`:
   - `/root/.ollama`: Model manifests and weight blobs.

---

## 8. Backup & Recovery

MRPL Workbench includes automated backup and restore scripts with cryptographic SHA-256 manifest verification.

### Creating a Backup
```bash
# Backup the active Docker persistent volume
python scripts/backup.py --volume mrpl_data --output-dir ./backups

# Output: backups/mrpl_backup_YYYYMMDD_HHMMSS.tar.gz
```

### Restoring from Backup
```bash
# 1. Stop backend container to release SQLite database lock
docker compose stop backend

# 2. Restore data into the mrpl_data Docker volume
python scripts/restore.py --archive ./backups/mrpl_backup_YYYYMMDD_HHMMSS.tar.gz --volume mrpl_data --wipe-first

# 3. Restart backend
docker compose start backend
```

---

## 9. Air-Gapped Installation

For strictly disconnected / air-gapped environments:

1. **Pre-build Container Images**:
   ```bash
   docker save mrpl-llm-backend:latest | gzip > mrpl-backend.tar.gz
   docker save mrpl-llm-frontend:latest | gzip > mrpl-frontend.tar.gz
   docker save ollama/ollama:0.33.3 | gzip > ollama.tar.gz
   ```
2. **Export Ollama Model Weights**:
   Archive the provisioned `mrpl_ollama_data` volume:
   ```bash
   docker run --rm -v mrpl_ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama_models.tar.gz -C /data .
   ```
3. **Transfer and Load on Target Machine**:
   ```bash
   docker load < mrpl-backend.tar.gz
   docker load < mrpl-frontend.tar.gz
   docker load < ollama.tar.gz
   docker volume create mrpl_ollama_data
   docker run --rm -v mrpl_ollama_data:/data -v $(pwd):/backup alpine tar xzf /backup/ollama_models.tar.gz -C /data
   docker compose up -d
   ```

---

## 10. Troubleshooting

| Symptom | Probable Cause | Resolution |
| :--- | :--- | :--- |
| Backend fails on startup | Insecure `SECRET_KEY` or `FIRST_SUPERUSER_PASSWORD` | Set `SECRET_KEY` >= 32 chars and `FIRST_SUPERUSER_PASSWORD` >= 10 chars in `.env`. |
| `/health/ready` returns 503 | Ollama models not pulled | Run `docker compose exec ollama ollama pull llama3.2:latest` and `nomic-embed-text`. |
| SSE stream disconnected | Nginx proxy buffering active | Confirm `proxy_buffering off;` is set in `frontend/nginx.conf`. |
| 404 on `/docs` | OpenAPI disabled in production | Set `ENABLE_OPENAPI=true` in `.env` if API docs are intentionally permitted. |
| Permission denied in `/app/data` | Container user UID mismatch | Volume directories must be owned by UID 1000 (`appuser`). |
