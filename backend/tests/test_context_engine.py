import pytest
from app.core.context_engine.schemas import ContextCandidate
from app.core.context_engine.budget import TokenBudgetCalculator, TokenEstimator
from app.core.context_engine.assembly import ContextAssemblyPipeline
from app.core.context_engine.engine import ContextEngine

def test_token_estimation():
    estimator = TokenEstimator()
    assert estimator.estimate("1234") == 1
    assert estimator.estimate("12345678") == 2
    assert estimator.estimate("") == 0
    
def test_budget_calculator():
    calc = TokenBudgetCalculator(model_context_limit=1000, output_reserve=200, safety_margin=50)
    assert calc.available_input_budget == 750

def test_context_assembly_pipeline_prioritization():
    calc = TokenBudgetCalculator(model_context_limit=100, output_reserve=0, safety_margin=0)
    pipeline = ContextAssemblyPipeline(calc, TokenEstimator())
    
    # 3 candidates, 40 tokens each. Only 2 should fit (80 total).
    candidates = [
        ContextCandidate(id="3", type="memory", content="A" * 160, priority=3),
        ContextCandidate(id="1", type="system", content="B" * 160, priority=1),
        ContextCandidate(id="2", type="request", content="C" * 160, priority=2),
    ]
    
    package = pipeline.run(candidates)
    
    assert len(package.system_instructions) == 1
    assert package.system_instructions[0].id == "1"
    
    assert package.current_request is not None
    assert package.current_request.id == "2"
    
    assert len(package.semantic_memories) == 0
    assert len(package.truncation_events) == 1
    assert "Dropped candidate 3" in package.truncation_events[0]
    assert package.token_usage["system"] == 40
    assert package.token_usage["request"] == 40
    assert package.token_budget["used"] == 80

def test_context_assembly_pipeline_deduplication():
    calc = TokenBudgetCalculator(model_context_limit=1000, output_reserve=0, safety_margin=0)
    pipeline = ContextAssemblyPipeline(calc, TokenEstimator())
    
    candidates = [
        ContextCandidate(id="1", type="rag", content="Duplicate info", priority=5),
        ContextCandidate(id="2", type="memory", content="Duplicate info", priority=6),
    ]
    
    package = pipeline.run(candidates)
    
    # Only one should survive (the higher priority one)
    assert len(package.rag_context) == 1
    assert len(package.semantic_memories) == 0

def test_context_engine_generation_request_conversion():
    engine = ContextEngine(model_context_limit=8192)
    candidates = [
        ContextCandidate(id="sys1", type="system", content="You are AI.", priority=1),
        ContextCandidate(id="req1", type="request", content="Hi", priority=2),
        ContextCandidate(id="mem1", type="memory", content="User likes pizza", priority=3),
        ContextCandidate(id="rag1", type="rag", content="Pizza recipe", source="book", priority=4),
        ContextCandidate(id="msg1", type="message", content="Hello", metadata={"role": "user"}, priority=5),
        ContextCandidate(id="msg2", type="message", content="Hi there", metadata={"role": "assistant"}, priority=5),
    ]
    
    package = engine.assemble_context(candidates)
    gen_req = engine.convert_to_generation_request(package, "test-model")
    
    assert gen_req.model == "test-model"
    # Expected messages:
    # 1. System (You are AI.)
    # 2. System (Background context with memory and rag)
    # 3. User (Hello)
    # 4. Assistant (Hi there)
    # 5. User (Hi)
    assert len(gen_req.messages) == 5
    assert gen_req.messages[0].role == "system"
    assert "You are AI." in gen_req.messages[0].content
    
    assert gen_req.messages[1].role == "system"
    assert "Relevant Memories:\n- User likes pizza" in gen_req.messages[1].content
    assert "Reference Documents:\nSource (book):\nPizza recipe" in gen_req.messages[1].content
    
    assert gen_req.messages[2].role == "user"
    assert gen_req.messages[2].content == "Hello"
    
    assert gen_req.messages[-1].role == "user"
    assert gen_req.messages[-1].content == "Hi"
