from typing import List
from app.core.context_engine.schemas import ContextCandidate, ContextPackage
from app.core.context_engine.budget import TokenEstimator, TokenBudgetCalculator
from app.core.context_engine.assembly import ContextAssemblyPipeline
from app.core.model_gateway.schemas import GenerationRequest, Message

class ContextEngine:
    def __init__(self, model_context_limit: int = 8192):
        self.estimator = TokenEstimator()
        self.budget_calc = TokenBudgetCalculator(model_context_limit=model_context_limit)
        self.pipeline = ContextAssemblyPipeline(self.budget_calc, self.estimator)

    def assemble_context(self, candidates: List[ContextCandidate]) -> ContextPackage:
        return self.pipeline.run(candidates)

    def convert_to_generation_request(self, package: ContextPackage, model_id: str, stream: bool = False) -> GenerationRequest:
        """
        Converts a prioritized ContextPackage into a flattened GenerationRequest 
        for the Model Gateway.
        """
        messages = []

        # System Instructions
        sys_content = "\n\n".join([c.content for c in package.system_instructions])
        if sys_content:
            messages.append(Message(role="system", content=sys_content))

        # Memory / RAG / State / Summary (Appended as System context or Assistant Context)
        background_content = []
        if package.conversation_summary:
            background_content.append(f"Summary of previous conversation:\n{package.conversation_summary.content}")
        if package.semantic_memories:
            memories = "\n".join([f"- {c.content}" for c in package.semantic_memories])
            background_content.append(f"Relevant Memories:\n{memories}")
        if package.rag_context:
            rag = "\n\n".join([f"Source ({c.source}):\n{c.content}" for c in package.rag_context])
            background_content.append(f"Reference Documents:\n{rag}")
        if package.tool_context:
            tools = "\n\n".join([f"Tool Result ({c.source}):\n{c.content}" for c in package.tool_context])
            background_content.append(f"Tool Results:\n{tools}")
        if package.agent_state:
            background_content.append(f"Agent State:\n{package.agent_state.content}")

        if background_content:
            messages.append(Message(role="system", content="\n\n---\n\n".join(background_content)))

        # Chat History
        for msg in package.recent_messages:
            role = msg.metadata.get("role", "user")
            messages.append(Message(role=role, content=msg.content))

        # Current Request
        if package.current_request:
            messages.append(Message(role="user", content=package.current_request.content))

        return GenerationRequest(
            model=model_id,
            messages=messages,
            stream=stream,
            metadata={
                "truncation_events": package.truncation_events,
                "token_usage": package.token_usage
            }
        )
