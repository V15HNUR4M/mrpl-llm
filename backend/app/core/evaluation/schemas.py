import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class EvaluationCategory(str, Enum):
    RAG = "RAG"
    MEMORY = "MEMORY"
    AGENT = "AGENT"
    TOOL = "TOOL"
    WORKFLOW = "WORKFLOW"
    MULTIMODAL = "MULTIMODAL"
    MODEL_GATEWAY = "MODEL_GATEWAY"
    HALLUCINATION = "HALLUCINATION"
    ADVERSARIAL = "ADVERSARIAL"
    END_TO_END = "END_TO_END"

class EvaluationCase(BaseModel):
    case_id: str
    category: EvaluationCategory
    name: str
    description: str = ""
    input_data: Dict[str, Any] = Field(default_factory=dict)
    expected_facts: List[str] = Field(default_factory=list)
    forbidden_facts: List[str] = Field(default_factory=list)
    expected_sources: List[str] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    expected_state: Optional[str] = None
    thresholds: Dict[str, float] = Field(default_factory=dict)
    is_adversarial: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EvaluationDataset(BaseModel):
    dataset_id: str
    version: str
    description: str = ""
    cases: List[EvaluationCase]

    def get_by_category(self, category: EvaluationCategory) -> List[EvaluationCase]:
        return [c for c in self.cases if c.category == category]

    def validate_integrity(self) -> None:
        seen = set()
        for c in self.cases:
            if c.case_id in seen:
                raise ValueError(f"Duplicate case_id in dataset: {c.case_id}")
            seen.add(c.case_id)
            if not c.name or not c.category:
                raise ValueError(f"EvaluationCase {c.case_id} missing name or category")

class EvaluationResult(BaseModel):
    case_id: str
    category: EvaluationCategory
    passed: bool
    score: float = 1.0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    error: Optional[str] = None
    sanitized_output: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class EvaluationSummary(BaseModel):
    run_id: str
    dataset_version: str
    timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int = 0
    pass_rate: float
    category_summaries: Dict[str, Dict[str, Any]]
    metrics: Dict[str, Any]
    latency_p50_ms: float
    latency_p95_ms: float
    threshold_violations: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    provider: Optional[str] = None
