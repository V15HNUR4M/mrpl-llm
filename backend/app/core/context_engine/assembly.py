from typing import List
from app.core.context_engine.schemas import ContextCandidate, ContextPackage
from app.core.context_engine.budget import TokenEstimator, TokenBudgetCalculator

class ContextAssemblyPipeline:
    """
    Deterministic pipeline for context assembly:
    1. Collect Candidates
    2. Estimate Tokens
    3. Deduplicate
    4. Rank/Prioritize
    5. Truncate/Budget
    6. Assemble Package
    """
    def __init__(self, budget_calculator: TokenBudgetCalculator, estimator: TokenEstimator):
        self.budget_calc = budget_calculator
        self.estimator = estimator

    def run(self, candidates: List[ContextCandidate]) -> ContextPackage:
        # 1. Estimate tokens for all candidates
        for c in candidates:
            if c.token_count == 0:
                c.token_count = self.estimator.estimate_candidate(c)

        # 2. Deduplicate (simple exact content match for now)
        seen_content = set()
        deduped = []
        for c in candidates:
            if c.content not in seen_content:
                seen_content.add(c.content)
                deduped.append(c)

        # 3. Sort by Priority (lowest integer first), then relevance (highest first)
        ranked = sorted(deduped, key=lambda x: (x.priority, -x.relevance_score))

        # 4. Budget Enforcement
        available_budget = self.budget_calc.available_input_budget
        used_budget = 0
        accepted_candidates = []
        truncation_events = []
        token_usage = {}

        for c in ranked:
            if used_budget + c.token_count <= available_budget:
                accepted_candidates.append(c)
                used_budget += c.token_count
                token_usage[c.type] = token_usage.get(c.type, 0) + c.token_count
            else:
                truncation_events.append(f"Dropped candidate {c.id} (type: {c.type}) due to budget constraints.")
                # We could implement partial truncation here if needed, but dropping is safer for semantic blocks.

        # 5. Assemble Package
        package = ContextPackage(
            token_budget={"available": available_budget, "used": used_budget},
            token_usage=token_usage,
            truncation_events=truncation_events
        )

        for c in accepted_candidates:
            if c.type == "system":
                package.system_instructions.append(c)
            elif c.type == "request":
                package.current_request = c
            elif c.type == "message":
                package.recent_messages.append(c)
            elif c.type == "summary":
                package.conversation_summary = c
            elif c.type == "memory":
                package.semantic_memories.append(c)
            elif c.type == "rag":
                package.rag_context.append(c)
            elif c.type == "tool":
                package.tool_context.append(c)
            elif c.type == "agent_state":
                package.agent_state = c
            else:
                # Default bucket
                package.metadata[f"custom_{c.id}"] = c.model_dump()

        # Preserve ordering of recent messages by sorting by sequence_number instead of id
        package.recent_messages = sorted(package.recent_messages, key=lambda x: x.metadata.get("sequence_number", 0))

        return package
