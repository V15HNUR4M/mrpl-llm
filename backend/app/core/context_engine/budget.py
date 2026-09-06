from app.core.context_engine.schemas import ContextCandidate

class TokenEstimator:
    """
    Abstraction for estimating token counts.
    Uses the 1 token ≈ 4 characters approximation strategy.
    Can be replaced later by a proper tokenizer (like tiktoken) if exact counts are needed.
    """
    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    def estimate_candidate(self, candidate: ContextCandidate) -> int:
        return self.estimate(candidate.content)

class TokenBudgetCalculator:
    """
    Handles dynamic token budget allocation according to model constraints.
    """
    def __init__(self, model_context_limit: int, output_reserve: int = 2048, safety_margin: int = 256):
        self.model_context_limit = model_context_limit
        self.output_reserve = output_reserve
        self.safety_margin = safety_margin

    @property
    def available_input_budget(self) -> int:
        budget = self.model_context_limit - self.output_reserve - self.safety_margin
        return max(0, budget)
