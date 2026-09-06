# MRPL Sovereign On-Premise Agentic AI Workbench

# Model Gateway Design

## 1. Purpose

The Model Gateway is the single abstraction layer through which the MRPL AI Workbench communicates with local AI models.

Its primary responsibility is to prevent application components, agents, tools, and workflows from becoming directly coupled to:

* Qwen
* Llama
* Ollama
* vLLM
* LM Studio
* Any specific model API
* Any specific inference protocol

The gateway provides a stable internal interface while allowing the underlying model infrastructure to change.

The architectural rule is:

> Agents request model capabilities; the Model Gateway determines how those capabilities are provided.

---

# 2. Architectural Position

The Model Gateway sits between the Agent Harness and local model infrastructure.

```text
Frontend
    ↓
Application API
    ↓
Agent Harness
    ↓
Agent
    ↓
Model Gateway
    ↓
Provider Adapter
    ↓
Local Model Server
    ↓
Open-Weight Model
```

Example:

```text
Document Agent
      ↓
Model Gateway
      ↓
Ollama Adapter
      ↓
Qwen
```

The same agent should later be able to run:

```text
Document Agent
      ↓
Model Gateway
      ↓
vLLM Adapter
      ↓
Llama
```

without changing the agent implementation.

---

# 3. Design Goals

The Model Gateway must provide:

1. Provider abstraction
2. Model abstraction
3. Capability discovery
4. Text generation
5. Streaming generation
6. Embedding support
7. Vision support
8. Tool/function calling where supported
9. Model selection
10. Configuration management
11. Timeouts
12. Retries
13. Resource awareness
14. Usage tracking
15. Error normalization
16. Observability
17. Local-first operation
18. Replaceability

---

# 4. Non-Goals

The Model Gateway is not responsible for:

* Agent orchestration
* Conversation management
* RAG retrieval
* Memory management
* Tool authorization
* Business logic
* Prompt injection policy
* User authentication
* Workflow execution

Those responsibilities belong to other components.

---

# 5. Core Principle

The rest of the application should not care whether the model is running through:

```text
Ollama
vLLM
LM Studio
llama.cpp
Transformers
```

The application should interact with:

```text
ModelGateway
```

instead.

---

# 6. Provider Abstraction

A provider represents an inference backend.

Examples:

```text
ollama
vllm
lmstudio
llamacpp
transformers
```

A provider may expose one or more models.

Example:

```text
Provider: Ollama

Models:
- Qwen
- Llama
- Gemma
```

---

# 7. Model Abstraction

A model represents an actual AI model configuration.

Conceptually:

```text
Model

id
name
provider
version
capabilities
context_window
configuration
status
```

Example:

```text
model_id: qwen-local
provider: ollama
capabilities:
    text
    tool_calling
```

---

# 8. Capability-Based Design

Agents must request capabilities rather than hard-coded model names.

Example:

```text
Required capability:
vision
```

The gateway determines whether an appropriate local model exists.

Possible capabilities:

```text
TEXT_GENERATION
STREAMING
EMBEDDING
VISION
TOOL_CALLING
STRUCTURED_OUTPUT
LONG_CONTEXT
```

---

# 9. Capability Discovery

The gateway should expose model capabilities.

Conceptually:

```python
capabilities(model_id)
```

Example:

```json
{
  "model": "qwen-local",
  "capabilities": [
    "text_generation",
    "streaming",
    "vision",
    "tool_calling"
  ]
}
```

The capability registry should not be based solely on model names.

---

# 10. Model Selection

The gateway should support model selection based on:

* Requested capability
* Agent policy
* Configured default model
* Availability
* Context requirements
* Hardware constraints
* Task type

Example:

```text
Agent requires:
VISION + TEXT_GENERATION

        ↓

Model Gateway

        ↓

Find compatible local model

        ↓

Vision-capable model
```

---

# 11. Explicit Model Selection

The caller may optionally specify a model.

Example:

```text
model = "qwen-local"
```

However, the caller should not specify provider-specific connection details.

Bad:

```text
ollama_url
model_endpoint
provider_api_format
```

Good:

```text
model_id = qwen-local
```

---

# 12. Default Model

The platform should support a configured default model.

Example:

```text
DEFAULT_CHAT_MODEL=qwen-local
DEFAULT_EMBEDDING_MODEL=embedding-local
```

The gateway resolves the corresponding provider.

---

# 13. Fallback Models

Optional fallback models may be configured.

Example:

```text
Primary:
qwen-local

Fallback:
llama-local
```

Fallback should only occur when the fallback model satisfies the required capability.

The system must not silently switch to an incompatible model.

---

# 14. Local-Only Requirement

The gateway must support operation without cloud inference.

The critical path must be:

```text
Application
    ↓
Model Gateway
    ↓
Local Provider
    ↓
Local Model
```

Cloud providers may be supported as optional adapters in the future, but they must not be mandatory for core operation.

---

# 15. Provider Interface

Conceptually:

```python
class ModelProvider:

    async def generate(
        self,
        request,
    ):
        ...

    async def stream(
        self,
        request,
    ):
        ...

    async def embed(
        self,
        request,
    ):
        ...

    async def vision(
        self,
        request,
    ):
        ...

    async def tool_call(
        self,
        request,
    ):
        ...

    async def health(
        self,
    ):
        ...
```

Not every provider needs to implement every capability.

Unsupported operations must return explicit capability errors.

---

# 16. Model Gateway Interface

The application should interact with a gateway abstraction.

Conceptually:

```python
class ModelGateway:

    async def generate(
        self,
        request,
    ):
        ...

    async def stream(
        self,
        request,
    ):
        ...

    async def embed(
        self,
        request,
    ):
        ...

    async def vision(
        self,
        request,
    ):
        ...

    async def tool_call(
        self,
        request,
    ):
        ...

    async def get_model(
        self,
        model_id,
    ):
        ...

    async def list_models(
        self,
    ):
        ...
```

---

# 17. Generation Request

A generation request should be provider-neutral.

Conceptually:

```json
{
  "model": "qwen-local",
  "messages": [],
  "temperature": 0.2,
  "max_tokens": 1024,
  "stream": true,
  "metadata": {}
}
```

Provider-specific parameters should not leak into this contract unless explicitly supported as optional metadata.

---

# 18. Message Representation

The gateway should use a normalized message representation.

Example:

```json
{
  "role": "user",
  "content": "What issue was observed?"
}
```

Supported roles may include:

```text
system
user
assistant
tool
```

The gateway converts these into the provider-specific format.

---

# 19. Content Blocks

For multimodal requests, message content should support structured blocks.

Example:

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Analyze this image."
    },
    {
      "type": "image",
      "data": "...",
      "mime_type": "image/png"
    }
  ]
}
```

The gateway converts this representation for the selected provider.

---

# 20. Generation Response

The gateway should normalize provider responses.

Conceptually:

```json
{
  "text": "The observed issue was minor leakage.",
  "model": "qwen-local",
  "finish_reason": "stop",
  "usage": {
    "input_tokens": 450,
    "output_tokens": 30
  },
  "metadata": {}
}
```

---

# 21. Streaming Response

Streaming should return normalized events.

Example:

```json
{
  "type": "text_delta",
  "text": "The"
}
```

followed by:

```json
{
  "type": "text_delta",
  "text": " observed"
}
```

and finally:

```json
{
  "type": "completed"
}
```

---

# 22. Streaming Event Types

Suggested normalized events:

```text
generation_started
text_delta
tool_call_started
tool_call_delta
tool_call_completed
usage
generation_completed
generation_failed
```

Provider-specific event formats must be converted before reaching the Agent Harness.

---

# 23. Tool Calling

The Model Gateway may support normalized tool/function calling.

Conceptually:

```json
{
  "name": "search_documents",
  "arguments": {
    "query": "mechanical seal"
  }
}
```

The gateway reports the model's requested tool call.

It must not execute the tool.

---

# 24. Tool Execution Boundary

The architecture must remain:

```text
Model
 ↓
Model Gateway
 ↓
Agent Harness
 ↓
Tool Registry
 ↓
Authorization
 ↓
Tool
```

Never:

```text
Model
 ↓
Provider
 ↓
Arbitrary Tool Execution
```

The gateway only transports model-generated tool requests.

---

# 25. Structured Output

Where supported, the gateway should allow structured output.

Example:

```json
{
  "type": "object",
  "properties": {
    "issue": {
      "type": "string"
    },
    "severity": {
      "type": "string"
    }
  }
}
```

The gateway should normalize provider-specific structured-output mechanisms.

---

# 26. Structured Output Validation

Model output claiming to be JSON should not automatically be trusted.

The application should validate the output against the requested schema.

```text
Model
 ↓
Gateway
 ↓
Structured Output
 ↓
Schema Validation
 ↓
Agent
```

Malformed output should generate a controlled validation error.

---

# 27. Embeddings

Embedding generation should use the same provider abstraction philosophy.

```text
RAG
 ↓
Embedding Service
 ↓
Model Gateway
 ↓
Embedding Provider
 ↓
Local Embedding Model
```

The RAG implementation should not directly call Ollama or another provider.

---

# 28. Embedding Interface

Conceptually:

```python
class EmbeddingProvider:

    async def embed(
        self,
        texts,
    ):
        ...
```

The gateway should normalize:

```text
Input:
["text one", "text two"]

Output:
[
  [0.1, 0.2, ...],
  [0.3, 0.4, ...]
]
```

---

# 29. Embedding Model Independence

The application should identify embeddings by logical model ID.

Example:

```text
embedding-local
```

rather than:

```text
ollama/nomic-embed-text
```

This allows the embedding implementation to change later.

---

# 30. Embedding Dimension

The vector store must know the embedding dimension.

Example:

```text
embedding-local
dimension = 768
```

Changing embedding models may require re-indexing.

The system must detect incompatible dimensions rather than silently storing invalid vectors.

---

# 31. Vision Support

Vision requests should use the same gateway.

```text
Agent
 ↓
Model Gateway
 ↓
Vision-capable Provider
 ↓
Vision Model
```

The agent should request:

```text
vision capability
```

rather than directly selecting a provider.

---

# 32. Vision Input

Supported inputs may include:

* Image bytes
* Image references
* MIME type
* Text instructions

Example:

```text
image/png
image/jpeg
```

The gateway validates supported formats.

---

# 33. Multimodal Capability

The gateway should expose whether a model supports:

```text
text
image
audio
video
```

Only capabilities required by the initial project should be implemented.

The initial implementation should prioritize:

```text
text + image
```

---

# 34. Context Window

Each model should declare its context window.

Example:

```text
qwen-local
context_window = 32768
```

The Context Manager must use this information when building prompts.

The Agent Harness should not blindly assume a fixed token limit.

---

# 35. Output Token Limits

The gateway should enforce maximum output tokens.

Example:

```text
max_output_tokens = 2048
```

The final value should respect:

```text
model_context_window
-
input_tokens
```

---

# 36. Token Accounting

The gateway should return token usage when the provider supports it.

Example:

```json
{
  "input_tokens": 1500,
  "output_tokens": 350,
  "total_tokens": 1850
}
```

This information should be available to:

* Observability
* Evaluation
* Context management
* Performance analysis

---

# 37. Token Estimation

If the provider does not return exact token counts, the gateway may use an appropriate local tokenizer or estimate.

Estimated values must be distinguishable from provider-reported values.

---

# 38. Temperature

Generation configuration may include:

```text
temperature
```

Recommended default should be configurable.

Example:

```text
temperature = 0.2
```

Lower values are generally preferable for grounded enterprise question answering.

---

# 39. Sampling Parameters

Optional generation parameters may include:

```text
top_p
top_k
temperature
max_tokens
stop_sequences
seed
```

Only parameters supported by the normalized contract should be exposed.

Provider-specific options may remain inside adapter configuration.

---

# 40. System Prompt

The Model Gateway should accept system messages but should not construct business-specific system prompts.

Prompt construction belongs to:

```text
Context Manager
Agent
Prompt Configuration
```

The gateway's responsibility is transportation and provider normalization.

---

# 41. Context Manager Relationship

The correct flow is:

```text
Agent
 ↓
Context Manager
 ↓
Context Package
 ↓
Model Gateway
 ↓
Provider
```

The gateway must not retrieve:

* Conversation history
* Memory
* RAG documents
* User information

Those are upstream responsibilities.

---

# 42. Provider Adapter

Each inference backend should be isolated behind an adapter.

Example:

```text
providers/
├── base.py
├── ollama.py
├── vllm.py
└── lmstudio.py
```

The adapters convert normalized requests into provider-specific requests.

---

# 43. Ollama Adapter

The initial prototype may use an Ollama adapter.

```text
Model Gateway
      ↓
Ollama Adapter
      ↓
Ollama
      ↓
Local Model
```

The rest of the system must not directly depend on the adapter.

---

# 44. vLLM Adapter

A vLLM adapter may be introduced later.

```text
Model Gateway
      ↓
vLLM Adapter
      ↓
vLLM
      ↓
Open-Weight Model
```

The agent layer should remain unchanged.

---

# 45. LM Studio Adapter

LM Studio may be supported as another local provider if required.

The adapter should implement the same normalized interface.

---

# 46. Transformers Adapter

Direct local inference using Transformers may be considered for development or specialized use cases.

However, the initial architecture should prefer a dedicated local model server to simplify:

* Process isolation
* Model lifecycle
* API access
* Resource management
* Containerization

---

# 47. Provider Registration

Providers should be registered centrally.

Conceptually:

```python
provider_registry.register(
    "ollama",
    OllamaProvider(...)
)
```

The gateway resolves providers through this registry.

---

# 48. Model Registry

The system should maintain model metadata.

Example:

```text
Model Registry

qwen-local
    provider: ollama
    type: chat
    capabilities:
        text
        streaming
        vision

embedding-local
    provider: ollama
    type: embedding
    capabilities:
        embedding
```

---

# 49. Model Health

The gateway should expose model/provider health.

Possible states:

```text
AVAILABLE
UNAVAILABLE
STARTING
DEGRADED
UNKNOWN
```

Health checks should not require generating an actual user response unless necessary.

---

# 50. Provider Health

Example:

```text
Ollama
 ├── Reachable
 ├── Model available
 └── Model loaded
```

If the provider is unreachable, the gateway should return a normalized availability error.

---

# 51. Startup Validation

At application startup, the system may validate:

* Provider connectivity
* Required model availability
* Embedding model availability
* Model capabilities
* Configuration consistency

The application should clearly report missing required models.

---

# 52. Model Loading

The gateway should not necessarily control model loading directly.

For providers such as Ollama or vLLM, model lifecycle may be controlled by the provider.

The gateway should expose availability rather than assuming ownership of the underlying process.

---

# 53. Concurrency

The gateway should account for concurrent requests.

Potential controls:

```text
max_concurrent_generations
max_concurrent_embeddings
max_concurrent_vision_requests
```

These limits should protect local hardware.

---

# 54. GPU Resource Awareness

Local deployment may have limited GPU memory.

The gateway should expose enough information for the runtime to avoid unreasonable concurrent workloads.

Possible metadata:

```text
gpu_available
gpu_memory
model_memory_estimate
```

Hardware monitoring may be implemented separately.

---

# 55. Request Queueing

If local hardware cannot serve all requests simultaneously:

```text
Requests
   ↓
Gateway Queue
   ↓
Provider
   ↓
Model
```

The first prototype may rely on provider-level concurrency and introduce an explicit queue later.

---

# 56. Timeout Policy

Every model operation must have a timeout.

Examples:

```text
connect_timeout
generation_timeout
embedding_timeout
vision_timeout
```

Timeouts should be configurable.

---

# 57. Retry Policy

Retry only operations likely to succeed after a temporary failure.

Possible retryable failures:

```text
connection reset
temporary provider unavailable
transient timeout
```

Do not repeatedly retry:

```text
invalid request
unsupported capability
invalid model
authentication failure
```

For local deployments, authentication may not exist at the provider layer, but the abstraction should remain capable of supporting it.

---

# 58. Error Normalization

Provider-specific errors must be converted into common gateway errors.

Examples:

```text
MODEL_NOT_FOUND
PROVIDER_UNAVAILABLE
CAPABILITY_UNSUPPORTED
INVALID_REQUEST
CONTEXT_TOO_LARGE
GENERATION_TIMEOUT
GENERATION_FAILED
EMBEDDING_FAILED
VISION_UNSUPPORTED
TOOL_CALL_UNSUPPORTED
```

Agents should not need to understand Ollama/vLLM-specific errors.

---

# 59. Error Information

Errors should contain:

```text
error_code
message
provider
model
retryable
metadata
```

Internal stack traces should remain in logs rather than user responses.

---

# 60. Provider Failover

If configured:

```text
Primary Provider
      ↓
Failure
      ↓
Fallback Provider
```

Failover should occur only if:

* Fallback is enabled
* Capability is supported
* Policy permits it
* Request is safe to retry

---

# 61. No Silent Model Switching

For reproducibility, the gateway should record which model actually served the request.

Example:

```text
requested_model = qwen-local
actual_model = llama-local
fallback = true
```

The final execution metadata must preserve this information.

---

# 62. Model Metadata

Every response should make it possible to identify:

```text
provider
model
model_version
adapter
```

This information is required for evaluation and audit.

---

# 63. Prompt Version Tracking

Where prompts are versioned, the request metadata should include:

```text
prompt_version
agent_version
```

This allows later analysis of why an output changed.

---

# 64. Request Correlation

The gateway should accept:

```text
request_id
execution_id
agent_id
conversation_id
```

These values should propagate into logs and metrics.

---

# 65. Security

The Model Gateway is inside the trusted backend boundary.

The frontend must never call:

```text
Ollama
vLLM
LM Studio
```

directly.

Required:

```text
Frontend
 ↓
Backend
 ↓
Authorization
 ↓
Agent Harness
 ↓
Model Gateway
```

---

# 66. Provider Credentials

If a provider requires credentials in the future, credentials must be stored outside source code.

Examples:

```text
environment variables
secret manager
secure configuration
```

Secrets must not appear in:

* Prompts
* Logs
* Agent context
* Tool results
* Audit records

---

# 67. Network Isolation

In a sovereign deployment, model services should preferably be accessible only through the internal Docker/network boundary.

Example:

```text
Frontend
    ↓
Backend
    ↓
Internal Model Network
    ↓
Ollama/vLLM
```

The model server does not need to be publicly exposed.

---

# 68. Provider Configuration

Configuration should be externalized.

Example:

```yaml
models:
  default_chat: qwen-local
  default_embedding: embedding-local

providers:
  ollama:
    enabled: true
    base_url: http://ollama:11434
```

Provider-specific configuration should remain isolated from application logic.

---

# 69. Environment Configuration

Environment variables may override configuration.

Example:

```text
MRPL_DEFAULT_CHAT_MODEL
MRPL_DEFAULT_EMBEDDING_MODEL
MRPL_OLLAMA_URL
MRPL_VLLM_URL
```

Sensitive values should use secret configuration.

---

# 70. Configuration Validation

Startup configuration validation should detect:

* Missing provider
* Missing model
* Invalid model ID
* Duplicate model IDs
* Unsupported capability
* Invalid context size
* Invalid endpoint
* Invalid generation settings

The application should fail clearly rather than failing later during user requests.

---

# 71. Model Gateway and RAG

RAG uses the gateway for embeddings.

```text
Document
 ↓
Chunk
 ↓
Model Gateway
 ↓
Embedding Model
 ↓
Vector Store
```

During retrieval:

```text
Query
 ↓
Model Gateway
 ↓
Query Embedding
 ↓
Vector Store
```

The RAG layer should never directly depend on a particular embedding provider.

---

# 72. Model Gateway and Memory

Semantic memory also uses embeddings.

```text
Memory
 ↓
Embedding Service
 ↓
Model Gateway
 ↓
Local Embedding Model
```

This allows memory and RAG to share infrastructure while remaining logically separate.

---

# 73. Model Gateway and Agents

The Agent Harness controls agent-to-model interaction.

```text
Agent
 ↓
Agent Harness
 ↓
Context Manager
 ↓
Model Gateway
 ↓
Model
```

An agent should not instantiate a provider.

---

# 74. Model Gateway and Multimodal Processing

For multimodal requests:

```text
Input Processor
 ↓
Agent Harness
 ↓
Context Manager
 ↓
Model Gateway
 ↓
Vision Model
```

The gateway handles provider-specific multimodal formatting.

---

# 75. Model Gateway and Evaluation

The gateway should expose metadata needed for evaluation.

At minimum:

```text
model
provider
latency
input_tokens
output_tokens
finish_reason
error
```

This allows comparison between models.

---

# 76. Benchmarking

The platform should support model benchmarking.

Metrics may include:

```text
first_token_latency
total_latency
tokens_per_second
input_tokens
output_tokens
memory_usage
GPU_usage
error_rate
```

Accuracy evaluation belongs to the Evaluation subsystem.

---

# 77. Model Comparison

Because of the gateway abstraction, the same evaluation dataset can be executed against:

```text
Qwen
Llama
Other Open-Weight Model
```

without modifying the application.

This is an important architectural benefit.

---

# 78. Deterministic Evaluation

For evaluation, the gateway should support controlled generation parameters.

Where supported:

```text
temperature = 0
seed = fixed
```

However, exact determinism cannot be assumed across different providers or hardware.

---

# 79. Context Overflow Handling

If the provider reports:

```text
CONTEXT_TOO_LARGE
```

the gateway should return a normalized error.

The gateway should not arbitrarily truncate context.

Context reduction belongs to the Context Manager.

---

# 80. Model Selection and Context

The gateway may expose:

```text
context_window
```

The Context Manager can then calculate:

```text
available_context =
model_context_window
-
reserved_output_tokens
```

This avoids the previous problem of assuming a fixed token budget for every model.

---

# 81. Reserved Output Budget

A model request should reserve output space.

Example:

```text
Context window = 8192
Reserved output = 1024

Available input = 7168
```

The Context Manager should build input accordingly.

---

# 82. Long-Context Models

A model supporting a larger context window may allow more retrieved information.

However, larger context should not automatically mean sending everything.

The Context Manager remains responsible for relevance and compression.

---

# 83. Provider Adapter Testing

Each adapter should have independent tests.

Example:

```text
tests/
├── test_gateway.py
├── test_ollama_provider.py
└── test_vllm_provider.py
```

Provider integration tests may require a running local server.

---

# 84. Mock Provider

A mock provider should be available.

Example:

```python
class MockModelProvider:
    async def generate(self, request):
        return MockResponse(...)
```

This enables testing the Agent Harness without loading a real model.

---

# 85. Gateway Unit Tests

Test:

* Model resolution
* Provider resolution
* Capability validation
* Request normalization
* Response normalization
* Error normalization
* Timeout handling
* Retry behavior
* Fallback behavior
* Streaming
* Token accounting

---

# 86. Integration Tests

The prototype should test:

```text
FastAPI
 ↓
Agent Harness
 ↓
Model Gateway
 ↓
Ollama
 ↓
Qwen
```

This verifies the complete local inference path.

---

# 87. Failure Tests

Test cases should include:

```text
Provider unavailable
Model unavailable
Model overloaded
Invalid request
Context too large
Unsupported vision
Unsupported tool calling
Timeout
Malformed response
```

---

# 88. Provider Independence Test

A critical architectural test is:

```text
Run same agent
    ↓
Provider A

Run same agent
    ↓
Provider B
```

No agent source code should change between these tests.

---

# 89. Gateway API Boundary

The frontend should not directly access the Model Gateway.

The gateway is an internal backend service.

```text
Browser
   X
   │
   └── Direct model access prohibited

Browser
   ↓
FastAPI
   ↓
Agent Harness
   ↓
Model Gateway
```

---

# 90. API Exposure

The backend may expose model information through safe APIs.

Example:

```text
GET /api/models
GET /api/models/{model_id}
GET /api/models/health
```

These APIs should expose only information appropriate for the current user.

---

# 91. Administrative Model APIs

Administrative users may access:

```text
GET /api/admin/models
POST /api/admin/models
PUT /api/admin/models/{id}
DELETE /api/admin/models/{id}
```

These operations must be protected by RBAC.

The exact API surface should be finalized in `API_DESIGN.md`.

---

# 92. Model Registration

Models should be registered through configuration initially.

Dynamic registration can be introduced later.

Initial approach:

```text
config/models.yaml
```

Future:

```text
Model Registry Database
```

---

# 93. Model Lifecycle

Models may have states:

```text
CONFIGURED
AVAILABLE
UNAVAILABLE
DISABLED
```

A disabled model must not be selected for new executions.

---

# 94. Model Deactivation

Disabling a model must not delete historical execution records.

Historical records should retain the model identifier and version.

---

# 95. Version Tracking

A model should ideally record:

```text
logical_model_id
provider
model_name
model_version
quantization
```

Example:

```text
logical ID:
qwen-local

provider:
ollama

model:
qwen3

quantization:
Q4_K_M
```

Exact metadata depends on provider support.

---

# 96. Quantization Awareness

Quantization may affect:

* Memory usage
* Speed
* Accuracy

The gateway may expose quantization metadata for benchmarking.

Agents should not depend on a specific quantization.

---

# 97. Hardware-Aware Model Selection

Future versions may select models based on:

```text
GPU memory
CPU
RAM
quantization
context length
```

Example:

```text
Small GPU
 ↓
Quantized model

Large GPU
 ↓
Higher-capacity model
```

This should remain an optional policy layer.

---

# 98. Model Routing

Future routing could classify requests:

```text
Simple request
 ↓
Small model

Complex analysis
 ↓
Large model

Vision request
 ↓
Vision model
```

The routing logic should remain in the gateway/policy layer rather than inside individual agents.

---

# 99. Agent Model Policies

Agents may define preferences.

Example:

```yaml
model_policy:
  required_capabilities:
    - text_generation
  preferred_model: qwen-local
  allow_fallback: true
```

The policy must not bypass platform-level restrictions.

---

# 100. Gateway Security Boundary

The gateway must trust only authenticated internal callers.

The Agent Harness should establish the execution identity.

Example:

```text
execution_id
user_id
agent_id
permissions
```

The gateway should not blindly trust arbitrary metadata supplied by the frontend.

---

# 101. Audit Metadata

Model invocation events should contain:

```text
execution_id
conversation_id
user_id
agent_id
provider
model
model_version
timestamp
latency
token_usage
status
```

Prompt content should not automatically be copied into audit logs.

---

# 102. Privacy

The gateway should avoid storing prompts or outputs independently unless explicitly required.

The conversation and execution persistence layers are responsible for durable storage.

This prevents unnecessary duplication of potentially sensitive data.

---

# 103. Logging Policy

Logs should contain operational metadata such as:

```text
model
provider
latency
status
request_id
execution_id
```

Logs should not contain complete sensitive prompts or document contents by default.

---

# 104. Observability Metrics

Recommended metrics:

```text
model_requests_total
model_failures_total
model_request_latency
model_tokens_input
model_tokens_output
model_tokens_per_second
model_fallback_total
model_context_errors
provider_health
```

---

# 105. Health Endpoint

Conceptually:

```text
GET /internal/models/health
```

Response:

```json
{
  "providers": {
    "ollama": {
      "status": "available"
    }
  },
  "models": {
    "qwen-local": {
      "status": "available"
    }
  }
}
```

---

# 106. Startup Behavior

Recommended startup sequence:

```text
Backend Start
    ↓
Load Configuration
    ↓
Initialize Gateway
    ↓
Initialize Providers
    ↓
Validate Required Models
    ↓
Expose Application
```

The backend should clearly report non-critical unavailable optional models.

---

# 107. Graceful Degradation

If the vision model is unavailable:

```text
Text functionality
      ↓
Continue working
```

The platform should not necessarily become entirely unavailable.

If the primary chat model is unavailable, the system should use configured fallback behavior or clearly report the outage.

---

# 108. Dependency Isolation

Provider-specific packages should remain isolated.

Example:

```text
gateway/
    interfaces.py

providers/
    ollama/
    vllm/
```

The core application should import gateway interfaces rather than provider SDKs.

---

# 109. Recommended Python Structure

Conceptually:

```text
backend/
└── app/
    └── models/
        ├── gateway.py
        ├── registry.py
        ├── types.py
        ├── capabilities.py
        ├── errors.py
        └── providers/
            ├── base.py
            ├── ollama.py
            ├── vllm.py
            └── lmstudio.py
```

The exact structure may evolve.

---

# 110. Type Definitions

Normalized request/response types should be centralized.

Example:

```text
GenerationRequest
GenerationResponse
StreamEvent
EmbeddingRequest
EmbeddingResponse
VisionRequest
ToolCall
ModelInfo
ProviderInfo
UsageMetrics
```

---

# 111. Model Gateway Request Flow

```text
Agent
  ↓
Agent Harness
  ↓
Context Manager
  ↓
GenerationRequest
  ↓
Model Gateway
  ↓
Validate Model
  ↓
Validate Capability
  ↓
Resolve Provider
  ↓
Provider Adapter
  ↓
Local Model
```

---

# 112. Response Flow

```text
Local Model
  ↓
Provider Adapter
  ↓
Normalize Response
  ↓
Model Gateway
  ↓
Agent Harness
  ↓
Agent
  ↓
Final Result
```

---

# 113. Tool Call Response Flow

```text
Model
  ↓
Tool Call
  ↓
Provider Adapter
  ↓
Model Gateway
  ↓
Agent Harness
  ↓
Tool Registry
  ↓
Tool Result
  ↓
Agent
  ↓
Model Gateway
  ↓
Final Response
```

---

# 114. Embedding Flow

```text
Text
 ↓
RAG / Memory
 ↓
Embedding Request
 ↓
Model Gateway
 ↓
Embedding Provider
 ↓
Local Embedding Model
 ↓
Vector
```

---

# 115. Vision Flow

```text
Image
 ↓
Input Processor
 ↓
Context Manager
 ↓
Model Gateway
 ↓
Vision Provider
 ↓
Local Vision Model
 ↓
Normalized Response
 ↓
Agent
```

---

# 116. No Direct Provider Calls

The following pattern is prohibited:

```python
import ollama

response = ollama.chat(...)
```

inside:

* Agents
* RAG services
* Memory services
* API routes
* Workflow handlers

Provider calls must go through the gateway.

---

# 117. Dependency Inversion

Required:

```text
Agent
 ↓
ModelGateway Interface
 ↓
Provider Implementation
```

Not:

```text
Agent
 ↓
Ollama SDK
```

This is one of the most important architectural constraints.

---

# 118. Model Gateway and Docker

The gateway should communicate with model services through internal Docker networking.

Example:

```text
mrpl-backend
      │
      │ internal network
      ▼
mrpl-ollama
```

No host-specific URLs should be hard-coded into application source code.

---

# 119. Development Environment

Developers should be able to run:

```text
Backend
 ↓
Model Gateway
 ↓
Local Ollama
 ↓
Development Model
```

without external cloud services.

---

# 120. Production Environment

The same application architecture should support:

```text
Backend
 ↓
Model Gateway
 ↓
Ollama / vLLM
 ↓
Production Open-Weight Model
```

The provider implementation may change without modifying the agent architecture.

---

# 121. Migration: Ollama → vLLM

The intended migration should be approximately:

```text
Current:
Ollama Provider

Future:
vLLM Provider
```

while preserving:

```text
Agent
Harness
Context Manager
RAG
Memory
API
Frontend
```

Only provider configuration and adapter behavior should need significant changes.

---

# 122. Migration: Qwen → Llama

Similarly:

```text
Current:
Qwen

Future:
Llama
```

The logical model ID may remain:

```text
default-chat-model
```

while configuration changes the actual implementation.

---

# 123. Model Aliases

Model aliases may simplify configuration.

Example:

```text
default-chat-model
default-vision-model
default-embedding-model
```

These aliases resolve to actual registered models.

This prevents agents from hard-coding model names.

---

# 124. Recommended Initial Configuration

Example conceptual configuration:

```yaml
models:

  default_chat:
    id: qwen-local
    provider: ollama

  default_embedding:
    id: embedding-local
    provider: ollama

providers:

  ollama:
    enabled: true
    base_url: http://ollama:11434
```

The exact model names should remain configurable.

---

# 125. Initial Implementation Phase

Implement in this order:

```text
1. Gateway interfaces
2. Normalized request/response types
3. Provider registry
4. Model registry
5. Ollama adapter
6. Text generation
7. Streaming
8. Error normalization
9. Health checks
10. Embeddings
11. Capability discovery
12. Tool-call normalization
13. Vision support
```

---

# 126. Minimum Viable Gateway

The first usable gateway only needs:

```text
generate()
stream()
list_models()
health()
```

with:

```text
Ollama
+
Local Open-Weight Model
```

This should be completed before adding additional providers.

---

# 127. Second Phase

Add:

```text
embedding()
capability detection
tool calling
structured output
usage metrics
```

---

# 128. Third Phase

Add:

```text
vision()
provider fallback
hardware-aware routing
advanced model selection
benchmarking
```

---

# 129. Acceptance Criteria

The Model Gateway is complete when:

* Agents do not directly call Ollama.
* Agents do not directly call vLLM.
* RAG does not directly call embedding providers.
* Memory does not directly call embedding providers.
* Model requests use normalized interfaces.
* Provider-specific responses are normalized.
* Provider-specific errors are normalized.
* Model capabilities can be discovered.
* Models can be selected by logical ID.
* Local inference works without cloud APIs.
* Streaming works.
* Embeddings work.
* Vision support is capability-driven.
* Tool calls are transported but not executed by the gateway.
* Context limits are exposed.
* Token usage can be recorded.
* Timeouts are enforced.
* Retry behavior is controlled.
* Model fallback is explicit and auditable.
* Provider health can be checked.
* Model metadata is traceable.
* Mock providers can be used for testing.
* Ollama can be replaced without modifying agents.
* Qwen can be replaced without modifying agents.

---

# 130. Critical Rules

1. Agents must never directly call model providers.
2. RAG must never directly call embedding providers.
3. Memory must never directly call embedding providers.
4. The Model Gateway is the only application abstraction for model inference.
5. Provider-specific APIs must remain behind adapters.
6. Model capabilities must be explicit.
7. Unsupported capabilities must return controlled errors.
8. Tool calls must never execute directly inside the gateway.
9. Authorization remains outside the model provider.
10. The gateway must not retrieve conversation history.
11. The gateway must not retrieve memory.
12. The gateway must not retrieve RAG documents.
13. The gateway must not implement business logic.
14. The gateway must not silently switch models.
15. Fallback model usage must be recorded.
16. Context overflow must be handled by the Context Manager.
17. Local inference must remain fully functional without cloud services.
18. Provider replacement must not require agent rewrites.
19. Model replacement must not require application rewrites.
20. All important model operations must be observable.

---

# 131. Final Architecture

```text
                         ┌───────────────────┐
                         │   Agent Harness   │
                         └─────────┬─────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │   Model Gateway   │
                         └─────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              Model Registry  Capability     Policy/
                             Resolution       Selection
                    │
                    ▼
              Provider Registry
                    │
          ┌─────────┼─────────┐
          │         │         │
          ▼         ▼         ▼
       Ollama     vLLM     LM Studio
          │         │         │
          ▼         ▼         ▼
        Qwen      Llama    Other Models
```

For embeddings:

```text
RAG / Memory
      ↓
Model Gateway
      ↓
Embedding Provider
      ↓
Local Embedding Model
```

For multimodal:

```text
Agent
      ↓
Model Gateway
      ↓
Vision-capable Provider
      ↓
Open-Weight Vision Model
```

---

# 132. Design Summary

The Model Gateway is the abstraction that makes the MRPL platform genuinely model-independent.

The architecture should allow:

```text
Qwen → Llama
Ollama → vLLM
Embedding Model A → Embedding Model B
Vision Model A → Vision Model B
```

without requiring changes to the agents, RAG architecture, memory architecture, or frontend.

The critical separation is:

```text
WHAT THE AI SHOULD DO
        ↓
       Agent

HOW THE AI IS EXECUTED
        ↓
   Agent Harness

WHICH MODEL PROVIDES INTELLIGENCE
        ↓
   Model Gateway

HOW THAT MODEL IS SERVED
        ↓
 Provider Adapter

WHERE THE MODEL RUNS
        ↓
 Local Model Server
```

This separation is essential for maintaining sovereignty, portability, testability, and long-term maintainability of the MRPL AI Workbench.
