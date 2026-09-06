# MRPL Sovereign On-Premise Agentic AI Workbench

# Evaluation

## 1. Purpose

Evaluation measures the quality and operational suitability of the MRPL AI Workbench.

Testing determines whether software behaves according to its implementation contract. Evaluation determines whether the resulting AI system is useful, grounded, reliable, safe, and efficient.

Evaluation must cover both individual models and the complete agentic system.

---

## 2. Evaluation Principles

1. Use versioned datasets.
2. Compare systems under equivalent conditions.
3. Separate model quality from infrastructure performance.
4. Evaluate retrieval independently from generation.
5. Evaluate tool use independently from final-answer quality.
6. Record configuration and model versions.
7. Maintain regression baselines.
8. Include adversarial and failure cases.
9. Prefer reproducible automated evaluation where possible.
10. Use human evaluation for qualities that automated metrics cannot reliably capture.

---

## 3. Evaluation Dimensions

The platform should evaluate:

- correctness
- relevance
- groundedness
- instruction following
- retrieval quality
- citation/source correctness
- tool-selection accuracy
- tool-argument correctness
- workflow correctness
- memory usefulness
- multimodal understanding
- safety and policy compliance
- latency
- throughput
- resource efficiency
- reliability

---

## 4. Evaluation Dataset

Datasets should be versioned.

Recommended categories:

```text
qa/
rag/
multiturn/
memory/
tool_use/
workflow/
multimodal/
long_context/
adversarial/
regression/
```

Each case should contain, where applicable:

```text
case_id
input
expected_behavior
reference_answer
authorized_sources
expected_tools
expected_workflow
difficulty
tags
dataset_version
```

Sensitive MRPL data must remain within the sovereign environment.

---

## 5. RAG Evaluation

RAG should be evaluated independently from generation.

Important metrics include:

### Recall@K

Measures whether the required evidence appears in the retrieved top-K results.

### Precision@K

Measures how much of the retrieved material is relevant.

### Source Hit Rate

Measures whether the correct source document or section was retrieved.

### Ranking Quality

Measures whether the most useful evidence appears near the top.

### Groundedness

Measures whether answer claims are supported by retrieved evidence.

### Unsupported Claim Rate

Measures claims that are not supported by the supplied evidence.

A strong RAG system should not merely retrieve similar text; it should retrieve evidence sufficient to answer the question.

---

## 6. Agent Evaluation

Agent behavior should be evaluated using task-level cases.

Measure:

```text
tool selection accuracy
tool argument accuracy
workflow selection
workflow argument accuracy
task completion
number of unnecessary actions
stop-condition correctness
policy compliance
failure recovery
```

Example:

```text
Question
   |
   v
Expected tool: document_search
   |
   v
Actual tool: document_search
   |
   v
Correct arguments?
   |
   v
Correct final answer?
```

An agent that produces a correct answer through an unauthorized action must still fail evaluation.

---

## 7. Memory Evaluation

Memory should be tested for:

- retrieval of useful previous information
- rejection of irrelevant memories
- stale-memory handling
- conflicting-memory handling
- memory isolation
- correct persistence
- correct invalidation
- prevention of unauthorized memory access

Evaluation should distinguish between:

```text
Useful memory
Irrelevant memory
Incorrect memory
Stale memory
Conflicting memory
```

---

## 8. Multimodal Evaluation

Multimodal cases should cover:

- image understanding
- OCR-sensitive documents
- tables
- charts
- scanned reports
- mixed text/image inputs

The evaluation must verify both extraction quality and downstream reasoning.

A model must not receive a passing score merely because it produces a plausible answer; the answer must correspond to the supplied evidence.

---

## 9. Model Comparison

When comparing local models:

```text
same dataset
same prompts
same retrieval configuration
same tool definitions
same evaluation policy
same hardware where possible
```

Record:

```text
model
model version
quantization
context length
runtime
hardware
temperature/sampling settings
dataset version
```

This prevents misleading comparisons caused by configuration differences.

---

## 10. Performance Evaluation

Record:

- time to first token (TTFT)
- total latency
- tokens per second
- request throughput
- queue time
- CPU usage
- RAM usage
- GPU/VRAM usage
- concurrent request capacity
- failure rate

Performance should be evaluated at realistic workloads rather than only single-user tests.

---

## 11. Human Evaluation

Human reviewers should score representative outputs using a consistent rubric.

Suggested dimensions:

| Dimension | Question |
|---|---|
| Correctness | Is the answer factually correct? |
| Groundedness | Is it supported by available evidence? |
| Relevance | Does it answer the actual request? |
| Clarity | Is it understandable? |
| Completeness | Does it cover required information? |
| Safety | Does it avoid unsafe/unauthorized behavior? |

Reviewers should be able to inspect retrieved sources and actions taken.

---

## 12. Regression Evaluation

An approved baseline should be maintained.

Whenever a model, prompt, retrieval configuration, context strategy, or agent implementation changes:

```text
New version
    |
    v
Regression dataset
    |
    v
Compare against baseline
    |
    +--> improved
    +--> unchanged
    +--> regression
```

A change that improves one metric while causing unacceptable regressions elsewhere should not automatically be promoted.

---

## 13. Evaluation Report

Every formal evaluation should record:

```text
evaluation_id
date
system version
agent version
model/version
runtime
hardware
dataset/version
configuration
metrics
failures
baseline comparison
decision
```

Results should be persisted so historical comparisons remain possible.

---

## 14. Release Gates

A release should be blocked when it causes unacceptable:

- security regressions
- grounding regressions
- correctness regressions
- authorization failures
- data-isolation failures
- critical reliability regressions

Performance thresholds should be defined according to deployment requirements.

---

## 15. Acceptance Criteria

The evaluation framework is complete when:

- datasets are versioned
- RAG is evaluated independently
- agent behavior is evaluated
- memory is evaluated
- multimodal behavior is evaluated
- performance is measured
- regression baselines exist
- human review is supported
- evaluation reports are reproducible
- release decisions are evidence-based
