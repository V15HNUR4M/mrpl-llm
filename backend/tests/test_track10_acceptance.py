"""
Track 10 - Observability Acceptance Tests
"""

import pytest
import pytest_asyncio
from typing import Optional, List


class CapturingObservabilityService:
    def __init__(self):
        self.events = []
        self.metrics = {"counters": {}, "gauges": {}, "average_latencies_ms": {}}
        self._fail_next = False

    def arm_failure(self):
        self._fail_next = True

    async def emit_event(self, event) -> Optional[str]:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("Injected observability failure")
        self.events.append(event.model_dump())
        return f"evt-{len(self.events)}"

    def record_metric(self, name, value=1.0, is_latency=False):
        if is_latency:
            self.metrics["average_latencies_ms"][name] = value
        else:
            self.metrics["counters"][name] = self.metrics["counters"].get(name, 0) + int(value)

    async def get_events(self, **kwargs): return self.events
    async def get_event_by_id(self, event_id, **kwargs): return None
    async def get_metrics(self, **kwargs): return self.metrics

    async def get_health(self):
        from app.core.observability.schemas import HealthStatus, DependencyHealth
        from datetime import datetime, timezone
        return HealthStatus(
            status="healthy", liveness=True, readiness=True,
            timestamp=datetime.now(timezone.utc),
            dependencies={"database": DependencyHealth(status="healthy")}
        )

    async def cleanup_retention(self, max_age_days=30, max_rows=50000): return 0


class TestEventTypeConstants:
    def test_model_generation_constants(self):
        from app.core.observability.schemas import (
            EVENT_MODEL_GEN_STARTED, EVENT_MODEL_GEN_COMPLETED, EVENT_MODEL_GEN_FAILED,
            EVENT_MODEL_STREAM_STARTED, EVENT_MODEL_STREAM_COMPLETED, EVENT_MODEL_STREAM_FAILED,
        )
        assert EVENT_MODEL_GEN_STARTED == "model.generation.started"
        assert EVENT_MODEL_GEN_COMPLETED == "model.generation.completed"
        assert EVENT_MODEL_GEN_FAILED == "model.generation.failed"
        assert EVENT_MODEL_STREAM_STARTED == "model.stream.started"
        assert EVENT_MODEL_STREAM_COMPLETED == "model.stream.completed"
        assert EVENT_MODEL_STREAM_FAILED == "model.stream.failed"

    def test_agent_constants(self):
        from app.core.observability.schemas import (
            EVENT_AGENT_RUN_STARTED, EVENT_AGENT_RUN_COMPLETED, EVENT_AGENT_RUN_FAILED,
        )
        assert EVENT_AGENT_RUN_STARTED == "agent.run.started"
        assert EVENT_AGENT_RUN_COMPLETED == "agent.run.completed"
        assert EVENT_AGENT_RUN_FAILED == "agent.run.failed"

    def test_tool_constants(self):
        from app.core.observability.schemas import (
            EVENT_TOOL_EXEC_STARTED, EVENT_TOOL_EXEC_COMPLETED,
            EVENT_TOOL_EXEC_DENIED, EVENT_TOOL_EXEC_FAILED,
        )
        assert EVENT_TOOL_EXEC_STARTED == "tool.execution.started"
        assert EVENT_TOOL_EXEC_COMPLETED == "tool.execution.completed"
        assert EVENT_TOOL_EXEC_DENIED == "tool.execution.denied"
        assert EVENT_TOOL_EXEC_FAILED == "tool.execution.failed"

    def test_workflow_constants(self):
        from app.core.observability.schemas import (
            EVENT_WORKFLOW_RUN_STARTED, EVENT_WORKFLOW_RUN_COMPLETED,
            EVENT_WORKFLOW_RUN_FAILED, EVENT_WORKFLOW_RUN_TIMEOUT, EVENT_WORKFLOW_RUN_CANCELLED,
        )
        assert EVENT_WORKFLOW_RUN_STARTED == "workflow.run.started"
        assert EVENT_WORKFLOW_RUN_COMPLETED == "workflow.run.completed"
        assert EVENT_WORKFLOW_RUN_FAILED == "workflow.run.failed"
        assert EVENT_WORKFLOW_RUN_TIMEOUT == "workflow.run.timeout"
        assert EVENT_WORKFLOW_RUN_CANCELLED == "workflow.run.cancelled"

    def test_rag_multimodal_constants(self):
        from app.core.observability.schemas import (
            EVENT_RAG_QUERY, EVENT_MULTIMODAL_ATTACHMENT, EVENT_MULTIMODAL_OCR
        )
        assert EVENT_RAG_QUERY == "rag.query"
        assert EVENT_MULTIMODAL_ATTACHMENT == "multimodal.attachment"
        assert EVENT_MULTIMODAL_OCR == "multimodal.ocr"


class TestTelemetryEventSchema:
    def test_minimal_valid_event(self):
        from app.core.observability.schemas import TelemetryEventCreate
        event = TelemetryEventCreate(event_type="test.event", component="test_comp")
        assert event.event_type == "test.event"
        assert event.component == "test_comp"
        assert event.severity == "INFO"
        assert event.metadata == {}

    def test_all_fields_populated(self):
        from app.core.observability.schemas import TelemetryEventCreate
        event = TelemetryEventCreate(
            event_type="model.generation.completed",
            component="model_gateway",
            severity="WARN",
            user_id="user_123",
            request_id="req_456",
            correlation_id="corr_789",
            duration_ms=250,
            status="success",
            metadata={"model": "qwen2.5"}
        )
        assert event.user_id == "user_123"
        assert event.duration_ms == 250
        assert event.metadata["model"] == "qwen2.5"

    def test_severity_accepts_all_levels(self):
        from app.core.observability.schemas import TelemetryEventCreate
        for sev in ("DEBUG", "INFO", "WARN", "ERROR"):
            e = TelemetryEventCreate(event_type="t", component="c", severity=sev)
            assert e.severity == sev

    def test_invalid_severity_rejected(self):
        from app.core.observability.schemas import TelemetryEventCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TelemetryEventCreate(event_type="t", component="c", severity="CRITICAL")

    def test_default_metadata_is_empty_dict(self):
        from app.core.observability.schemas import TelemetryEventCreate
        e = TelemetryEventCreate(event_type="t", component="c")
        assert isinstance(e.metadata, dict)
        assert len(e.metadata) == 0


class TestMetricsRegistry:
    def test_increment_counter(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.increment("test_counter")
        reg.increment("test_counter")
        assert reg.get_counter("test_counter") == 2

    def test_increment_by_amount(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.increment("tokens", 50)
        reg.increment("tokens", 25)
        assert reg.get_counter("tokens") == 75

    def test_latency_average(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.record_latency("op_lat", 100.0)
        reg.record_latency("op_lat", 200.0)
        snap = reg.get_snapshot()
        assert snap["average_latencies_ms"]["op_lat"] == 150.0

    def test_gauge_set(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.set_gauge("mem_mb", 512.0)
        reg.set_gauge("mem_mb", 256.0)
        snap = reg.get_snapshot()
        assert snap["gauges"]["mem_mb"] == 256.0

    def test_snapshot_structure(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        snap = reg.get_snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert "average_latencies_ms" in snap

    def test_reset_clears_all(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.increment("cnt", 10)
        reg.set_gauge("gauge", 1.0)
        reg.record_latency("lat", 50.0)
        reg.reset()
        snap = reg.get_snapshot()
        assert snap["counters"] == {}
        assert snap["gauges"] == {}
        assert snap["average_latencies_ms"] == {}

    def test_unknown_counter_returns_zero(self):
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()
        assert reg.get_counter("non_existent") == 0

    def test_thread_safety_no_exception(self):
        from app.core.observability.metrics import MetricsRegistry
        import threading
        reg = MetricsRegistry()
        errors = []

        def worker():
            try:
                for _ in range(100):
                    reg.increment("thread_counter")
                    reg.record_latency("thread_lat", 10.0)
                    reg.get_snapshot()
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        assert reg.get_counter("thread_counter") == 500


class TestRedaction:
    def test_password_is_redacted(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"password": "secret", "user": "alice"})
        assert result["password"] == "[REDACTED]"
        assert result["user"] == "alice"

    def test_token_is_redacted(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"access_token": "ey...", "token": "xyz"})
        assert result["access_token"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_api_key_is_redacted(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"api_key": "sk-1234", "apikey": "sk-5678"})
        assert result["api_key"] == "[REDACTED]"
        assert result["apikey"] == "[REDACTED]"

    def test_prompt_text_is_omitted(self):
        from app.core.observability.redaction import sanitize_metadata
        long_prompt = "Explain quantum computing in detail" * 10
        result = sanitize_metadata({"prompt": long_prompt})
        assert result["prompt"] == "[PROMPT_OMITTED]"
        assert result["prompt_length"] == len(long_prompt)

    def test_response_text_is_omitted(self):
        from app.core.observability.redaction import sanitize_metadata
        resp = "Quantum computing uses qubits..."
        result = sanitize_metadata({"response": resp})
        assert result["response"] == "[RESPONSE_OMITTED]"
        assert result["response_length"] == len(resp)

    def test_binary_data_key(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"blob_payload": b"\x89PNG\r\n\x1a\n"})
        assert "[BINARY_DATA_" in result["blob_payload"]

    def test_base64_image_key_omitted(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"images": "some_base64_data"})
        assert result["images"] == "[BINARY_OMITTED]"

    def test_safe_metadata_passes_through(self):
        from app.core.observability.redaction import sanitize_metadata
        meta = {"model": "qwen2.5", "temperature": 0.7, "step_count": 3}
        assert sanitize_metadata(meta) == meta

    def test_nested_redaction(self):
        from app.core.observability.redaction import sanitize_metadata
        meta = {"config": {"auth": {"api_key": "topsecret"}}}
        cleaned = sanitize_metadata(meta)
        assert cleaned["config"]["auth"]["api_key"] == "[REDACTED]"

    def test_max_depth_limit(self):
        from app.core.observability.redaction import sanitize_metadata
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}
        cleaned = sanitize_metadata(deep, max_depth=3)
        assert cleaned["a"]["b"]["c"] == "[MAX_DEPTH_REACHED]"

    def test_very_long_string_truncated(self):
        from app.core.observability.redaction import sanitize_metadata
        huge_str = "x" * 5000
        cleaned = sanitize_metadata({"note": huge_str})
        assert "TRUNCATED" in cleaned["note"]
        assert len(cleaned["note"]) < 5000

    def test_list_values_sanitized(self):
        from app.core.observability.redaction import sanitize_metadata
        data = [{"token": "tok1"}, {"token": "tok2"}]
        cleaned = sanitize_metadata(data)
        assert all(item["token"] == "[REDACTED]" for item in cleaned)

    def test_secret_key_redacted(self):
        from app.core.observability.redaction import sanitize_metadata
        result = sanitize_metadata({"client_secret": "xyz", "jwt_secret": "abc"})
        assert result["client_secret"] == "[REDACTED]"
        assert result["jwt_secret"] == "[REDACTED]"


@pytest.mark.asyncio
class TestObservabilityServiceMetrics:
    def _make_service(self):
        from app.core.observability.service import ObservabilityService
        from app.core.observability.metrics import MetricsRegistry
        reg = MetricsRegistry()

        class DummyUoW:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            class telemetry_events:
                @staticmethod
                def add(e): pass
                @staticmethod
                async def count_events(**kw): return 0
            async def commit(self): pass

        return ObservabilityService(uow=DummyUoW(), metrics=reg), reg

    async def test_model_events_update_counter(self):
        from app.core.observability.schemas import TelemetryEventCreate
        svc, reg = self._make_service()
        evt = TelemetryEventCreate(event_type="model.generation.started", component="model_gateway", status="started")
        await svc.emit_event(evt)
        assert reg.get_counter("model_requests_total") == 1

    async def test_failure_increments_counter(self):
        from app.core.observability.schemas import TelemetryEventCreate
        svc, reg = self._make_service()
        evt = TelemetryEventCreate(event_type="model.generation.failed", component="model_gateway", status="failed")
        await svc.emit_event(evt)
        assert reg.get_counter("model_gateway_failures_total") == 1

    async def test_tool_denial_counter(self):
        from app.core.observability.schemas import TelemetryEventCreate
        svc, reg = self._make_service()
        evt = TelemetryEventCreate(event_type="tool.execution.denied", component="tools", status="denied")
        await svc.emit_event(evt)
        assert reg.get_counter("tool_denials_total") == 1

    async def test_rag_empty_result_counter(self):
        from app.core.observability.schemas import TelemetryEventCreate
        svc, reg = self._make_service()
        evt = TelemetryEventCreate(
            event_type="rag.query", component="rag", status="success",
            metadata={"empty_result": True}
        )
        await svc.emit_event(evt)
        assert reg.get_counter("rag_empty_results_total") == 1

    async def test_token_counters(self):
        from app.core.observability.schemas import TelemetryEventCreate
        svc, reg = self._make_service()
        evt = TelemetryEventCreate(
            event_type="model.generation.completed", component="model_gateway",
            metadata={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
        )
        await svc.emit_event(evt)
        assert reg.get_counter("model_input_tokens_total") == 10
        assert reg.get_counter("model_output_tokens_total") == 20
        assert reg.get_counter("model_total_tokens_total") == 30

    async def test_db_failure_is_swallowed(self):
        from app.core.observability.service import ObservabilityService
        from app.core.observability.metrics import MetricsRegistry
        from app.core.observability.schemas import TelemetryEventCreate

        class BrokenUoW:
            async def __aenter__(self): raise ConnectionError("DB down")
            async def __aexit__(self, *a): pass

        svc = ObservabilityService(uow=BrokenUoW(), metrics=MetricsRegistry())
        evt = TelemetryEventCreate(event_type="test.event", component="test")
        result = await svc.emit_event(evt)
        assert result is None  # Resilient boundary: returns None, does not raise


@pytest.mark.asyncio
class TestModelGatewayTelemetry:
    def _fake_provider(self, fail=False):
        class FakeProvider:
            async def generate(self, req):
                if fail:
                    raise ValueError("provider failure")
                from app.core.model_gateway.schemas import GenerationResponse, Usage
                return GenerationResponse(text="hello", model="fake", usage=Usage())
            async def stream(self, req): return; yield
            async def get_model_info(self, model):
                from app.core.model_gateway.schemas import ModelInfo, ModelCapabilities
                return ModelInfo(model_id=model, provider="fake", capabilities=ModelCapabilities())
            async def health(self): return {"status": "ok"}
            async def list_models(self): return []
        return FakeProvider()

    async def test_generate_emits_started_and_completed(self):
        from app.core.model_gateway.gateway import ModelGateway
        from app.core.model_gateway.schemas import GenerationRequest, Message
        obs = CapturingObservabilityService()
        gw = ModelGateway(observability_service=obs)
        gw.register_provider("fake", self._fake_provider())
        gw.register_model_route("fake-model", "fake")
        req = GenerationRequest(model="fake-model", messages=[Message(role="user", content="hi")])
        await gw.generate(req)
        types = [e["event_type"] for e in obs.events]
        assert "model.generation.started" in types
        assert "model.generation.completed" in types

    async def test_generate_failure_emits_failed_event(self):
        from app.core.model_gateway.gateway import ModelGateway
        from app.core.model_gateway.schemas import GenerationRequest, Message
        obs = CapturingObservabilityService()
        gw = ModelGateway(observability_service=obs)
        gw.register_provider("fake", self._fake_provider(fail=True))
        gw.register_model_route("fail-model", "fake")
        req = GenerationRequest(model="fail-model", messages=[Message(role="user", content="hi")])
        with pytest.raises(ValueError):
            await gw.generate(req)
        types = [e["event_type"] for e in obs.events]
        assert "model.generation.failed" in types
        failed = next(e for e in obs.events if e["event_type"] == "model.generation.failed")
        assert failed["severity"] == "ERROR"

    async def test_gateway_works_without_observability_service(self):
        from app.core.model_gateway.gateway import ModelGateway
        from app.core.model_gateway.schemas import GenerationRequest, Message
        gw = ModelGateway()
        gw.register_provider("fake", self._fake_provider())
        gw.register_model_route("fake-model", "fake")
        req = GenerationRequest(model="fake-model", messages=[Message(role="user", content="test")])
        result = await gw.generate(req)
        assert result.text == "hello"

    async def test_completed_event_has_status_success(self):
        from app.core.model_gateway.gateway import ModelGateway
        from app.core.model_gateway.schemas import GenerationRequest, Message
        obs = CapturingObservabilityService()
        gw = ModelGateway(observability_service=obs)
        gw.register_provider("fake", self._fake_provider())
        gw.register_model_route("fake-model", "fake")
        req = GenerationRequest(model="fake-model", messages=[Message(role="user", content="hi")])
        await gw.generate(req)
        completed = next((e for e in obs.events if e["event_type"] == "model.generation.completed"), None)
        assert completed is not None
        assert completed["status"] == "success"
        assert completed["duration_ms"] is not None


@pytest.mark.asyncio
class TestToolExecutorTelemetry:
    def _make_executor(self, obs=None):
        from app.core.runtime.tool_executor import (
            ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor, Tool
        )
        class SimpleTestTool(Tool):
            @property
            def name(self): return "test_tool"
            @property
            def description(self): return "A test tool"
            @property
            def input_schema(self): return {"type": "object"}
            async def execute(self, arguments, context):
                from app.core.runtime.schemas import ToolResult
                return ToolResult(output="result", status="success")

        registry = ToolRegistry()
        registry.register(SimpleTestTool())
        local_exec = LocalToolExecutor(registry)
        return AuthorizedToolExecutor(local_exec, observability_service=obs)

    async def test_successful_tool_emits_started_and_completed(self):
        from app.core.runtime.tool_executor import ToolRequest
        obs = CapturingObservabilityService()
        executor = self._make_executor(obs)
        await executor.execute(ToolRequest(call_id="call-1", tool="test_tool", arguments={}), context={"user_id": "u1"})
        types = [e["event_type"] for e in obs.events]
        assert "tool.execution.started" in types
        assert "tool.execution.completed" in types

    async def test_denied_tool_emits_denied_event(self):
        from app.core.runtime.tool_executor import ToolRequest
        obs = CapturingObservabilityService()
        executor = self._make_executor(obs)
        # Not in allowed_tools list -> denial
        await executor.execute(ToolRequest(call_id="call-1", tool="test_tool", arguments={}),
                               context={"user_id": "u1"},
                               allowed_tools=["other_tool"])
        types = [e["event_type"] for e in obs.events]
        assert "tool.execution.denied" in types
        denied = next(e for e in obs.events if e["event_type"] == "tool.execution.denied")
        assert denied["severity"] == "WARN"

    async def test_observability_failure_does_not_break_tool(self):
        from app.core.runtime.tool_executor import ToolRequest
        obs = CapturingObservabilityService()
        obs.arm_failure()
        executor = self._make_executor(obs)
        result = await executor.execute(ToolRequest(call_id="call-1", tool="test_tool", arguments={}), context={"user_id": "u1"})
        assert result.status == "success"

    async def test_mcp_tool_emits_equivalent_telemetry(self):
        from app.core.runtime.tool_executor import (
            ToolRegistry, LocalToolExecutor, AuthorizedToolExecutor, Tool, ToolRequest
        )
        class SimpleMCPTool(Tool):
            @property
            def name(self): return "mcp_query"
            @property
            def description(self): return "MCP query tool"
            @property
            def input_schema(self): return {"type": "object"}
            async def execute(self, arguments, context):
                from app.core.runtime.schemas import ToolResult
                return ToolResult(output="mcp result", status="success")

        obs = CapturingObservabilityService()
        registry = ToolRegistry()
        registry.register(SimpleMCPTool())
        local_exec = LocalToolExecutor(registry)
        auth_exec = AuthorizedToolExecutor(local_exec, observability_service=obs)

        res = await auth_exec.execute(
            ToolRequest(call_id="call-mcp-1", tool="mcp_query", arguments={"q": "SELECT 1"}),
            context={"user_id": "u1", "request_id": "req-mcp-1"}
        )
        assert res.status == "success"
        types = [e["event_type"] for e in obs.events]
        assert "tool.execution.started" in types
        assert "tool.execution.completed" in types
        mcp_evt = next(e for e in obs.events if e["event_type"] == "tool.execution.completed")
        assert mcp_evt["metadata"]["tool"] == "mcp_query"


@pytest.mark.asyncio
class TestAgentHarnessTelemetry:
    def _make_harness(self, obs=None):
        from app.core.agent.registry import AgentRegistry, AgentDefinition
        from app.core.context_engine.engine import ContextEngine
        from app.core.runtime.tool_executor import ToolRegistry, LocalToolExecutor
        from app.core.runtime.harness import AgentHarness

        reg = AgentRegistry()
        reg.register(AgentDefinition(
            agent_id="test_agent", name="Test", description="Test",
            version="1.0", instructions="Be helpful."
        ))
        ce = ContextEngine()

        class FakeGateway:
            async def generate(self, req):
                from app.core.model_gateway.schemas import GenerationResponse, Usage
                return GenerationResponse(text="Hello from agent", model="fake", usage=Usage())

        tools = LocalToolExecutor(ToolRegistry())
        return AgentHarness(reg, ce, FakeGateway(), tools, observability_service=obs)

    async def test_agent_run_emits_started_and_completed(self):
        from app.core.runtime.schemas import RuntimeSession
        obs = CapturingObservabilityService()
        harness = self._make_harness(obs)
        session = RuntimeSession(session_id="s1", conversation_id="c1",
                                 agent_id="test_agent", agent_version="1.0", user_id="u1")
        await harness.execute(session, "Hello")
        types = [e["event_type"] for e in obs.events]
        assert "agent.run.started" in types
        assert "agent.run.completed" in types

    async def test_agent_telemetry_includes_agent_id(self):
        from app.core.runtime.schemas import RuntimeSession
        obs = CapturingObservabilityService()
        harness = self._make_harness(obs)
        session = RuntimeSession(session_id="s1", conversation_id="c1",
                                 agent_id="test_agent", agent_version="1.0", user_id="u1")
        await harness.execute(session, "Hello")
        start = next(e for e in obs.events if e["event_type"] == "agent.run.started")
        assert start["metadata"]["agent_id"] == "test_agent"

    async def test_harness_works_without_observability(self):
        from app.core.runtime.schemas import RuntimeSession
        harness = self._make_harness(None)
        session = RuntimeSession(session_id="s1", conversation_id="c1",
                                 agent_id="test_agent", agent_version="1.0", user_id="u1")
        decision = await harness.execute(session, "Hello")
        assert decision.final_answer == "Hello from agent"

    async def test_agent_completed_event_has_duration(self):
        from app.core.runtime.schemas import RuntimeSession
        obs = CapturingObservabilityService()
        harness = self._make_harness(obs)
        session = RuntimeSession(session_id="s1", conversation_id="c1",
                                 agent_id="test_agent", agent_version="1.0", user_id="u1")
        await harness.execute(session, "Hello")
        comp = next(e for e in obs.events if e["event_type"] == "agent.run.completed")
        assert comp["duration_ms"] is not None

    async def test_agent_emits_step_telemetry(self):
        from app.core.runtime.schemas import RuntimeSession
        obs = CapturingObservabilityService()
        harness = self._make_harness(obs)
        session = RuntimeSession(session_id="s_step", conversation_id="c_step",
                                 agent_id="test_agent", agent_version="1.0", user_id="u_step")
        await harness.execute(session, "Step test")
        types = [e["event_type"] for e in obs.events]
        assert "agent.step.started" in types
        assert "agent.step.completed" in types


@pytest.mark.asyncio
class TestWorkflowTelemetry:
    def _make_engine(self, obs=None):
        from app.core.workflow.engine import WorkflowEngine
        class DummyUoW:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            class audit:
                @staticmethod
                async def create(*a, **kw): pass
            async def commit(self): pass

        class DummyHarness:
            async def execute(self, session, input_val):
                from app.core.runtime.schemas import AgentDecision
                return AgentDecision(final_answer="agent response")

        class DummyExecutor:
            async def execute(self, req, context=None):
                from app.core.runtime.tool_executor import ToolResult
                return ToolResult(output="tool response", status="success")

        return WorkflowEngine(
            uow=DummyUoW(),
            agent_harness=DummyHarness(),
            tool_executor=DummyExecutor(),
            observability_service=obs
        )

    def _sample_spec(self):
        from app.core.workflow.schemas import WorkflowSpec, WorkflowStep, StepType
        return WorkflowSpec(
            start_step="step1",
            steps={
                "step1": WorkflowStep(
                    id="step1",
                    type=StepType.TOOL,
                    configuration={"tool": "dummy", "arguments": {}},
                    next_step="step2"
                ),
                "step2": WorkflowStep(
                    id="step2",
                    type=StepType.AGENT,
                    configuration={"agent_id": "test_agent", "input": "go"},
                    next_step=None
                )
            }
        )

    async def test_workflow_lifecycle_emits_started_step_and_completed(self):
        obs = CapturingObservabilityService()
        engine = self._make_engine(obs)
        status, ctx = await engine.execute(
            run_id="run-1",
            workflow_version_id="wv-1",
            user_id="user-1",
            spec=self._sample_spec(),
            inputs={}
        )
        types = [e["event_type"] for e in obs.events]
        assert "workflow.run.started" in types
        assert "workflow.step.completed" in types
        assert "workflow.run.completed" in types
        completed_evt = next(e for e in obs.events if e["event_type"] == "workflow.run.completed")
        assert completed_evt["status"] == "success"
        assert completed_evt["duration_ms"] is not None

    async def test_workflow_timeout_emits_distinct_timeout_event(self):
        from unittest.mock import patch
        import asyncio
        obs = CapturingObservabilityService()
        engine = self._make_engine(obs)
        with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
            status, ctx = await engine.execute(
                run_id="run-2",
                workflow_version_id="wv-2",
                user_id="user-1",
                spec=self._sample_spec(),
                inputs={}
            )
        types = [e["event_type"] for e in obs.events]
        assert "workflow.run.timeout" in types
        assert "workflow.run.failed" not in types  # Timeout is distinct, not collapsed
        t_evt = next(e for e in obs.events if e["event_type"] == "workflow.run.timeout")
        assert t_evt["status"] == "timed_out"

    async def test_workflow_cancelled_emits_distinct_cancelled_event(self):
        from unittest.mock import patch
        import asyncio
        obs = CapturingObservabilityService()
        engine = self._make_engine(obs)
        with patch("asyncio.timeout", side_effect=asyncio.CancelledError):
            status, ctx = await engine.execute(
                run_id="run-3",
                workflow_version_id="wv-3",
                user_id="user-1",
                spec=self._sample_spec(),
                inputs={}
            )
        types = [e["event_type"] for e in obs.events]
        assert "workflow.run.cancelled" in types
        assert "workflow.run.failed" not in types  # Cancelled is distinct, not collapsed
        c_evt = next(e for e in obs.events if e["event_type"] == "workflow.run.cancelled")
        assert c_evt["status"] == "cancelled"

    async def test_workflow_works_without_observability_service(self):
        from app.core.workflow.schemas import WorkflowRunState
        engine = self._make_engine(obs=None)
        status, ctx = await engine.execute(
            run_id="run-5",
            workflow_version_id="wv-5",
            user_id="user-1",
            spec=self._sample_spec(),
            inputs={}
        )
        assert status == WorkflowRunState.COMPLETED

    async def test_workflow_resilient_to_observability_failure(self):
        from app.core.workflow.schemas import WorkflowRunState
        obs = CapturingObservabilityService()
        obs.arm_failure()
        engine = self._make_engine(obs)
        status, ctx = await engine.execute(
            run_id="run-6",
            workflow_version_id="wv-6",
            user_id="user-1",
            spec=self._sample_spec(),
            inputs={}
        )
        assert status == WorkflowRunState.COMPLETED


@pytest.mark.asyncio
class TestRAGServiceTelemetry:
    def _make_rag(self, obs=None, results=None):
        from app.core.rag.service import RAGService

        class FakeVS:
            async def similarity_search(self, *a, **kw):
                return results or []

        class FakeEP:
            async def embed_text(self, text): return [0.1, 0.2]

        class FakeChunker: pass
        class FakePR: pass

        return RAGService(
            parser_registry=FakePR(),
            chunker=FakeChunker(),
            embedding_provider=FakeEP(),
            vector_store=FakeVS(),
            observability_service=obs
        )

    async def test_search_emits_rag_query_event(self):
        from app.core.rag.schemas import RetrievalQuery
        obs = CapturingObservabilityService()
        rag = self._make_rag(obs=obs)
        await rag.search_documents(RetrievalQuery(query="safety procedures", top_k=3, owner_id="u1"))
        types = [e["event_type"] for e in obs.events]
        assert "rag.query" in types

    async def test_rag_query_event_has_result_count(self):
        from app.core.rag.schemas import RetrievalQuery
        obs = CapturingObservabilityService()
        rag = self._make_rag(obs=obs)
        await rag.search_documents(RetrievalQuery(query="pipeline inspection", top_k=5, owner_id="u1"))
        evt = next(e for e in obs.events if e["event_type"] == "rag.query")
        assert "result_count" in evt["metadata"]
        assert evt["metadata"]["result_count"] == 0

    async def test_rag_empty_result_flagged(self):
        from app.core.rag.schemas import RetrievalQuery
        obs = CapturingObservabilityService()
        rag = self._make_rag(obs=obs, results=[])
        await rag.search_documents(RetrievalQuery(query="unknown term", top_k=3, owner_id="u1"))
        evt = next(e for e in obs.events if e["event_type"] == "rag.query")
        assert evt["metadata"]["empty_result"] is True

    async def test_rag_works_without_observability_service(self):
        from app.core.rag.schemas import RetrievalQuery
        rag = self._make_rag(obs=None)
        res = await rag.search_documents(RetrievalQuery(query="test", top_k=2))
        assert isinstance(res, list)


@pytest.mark.asyncio
class TestMultimodalServiceTelemetry:
    def _make_mm(self, obs=None):
        from app.core.multimodal.service import MultimodalService

        class DummyUoW:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            class attachments:
                @staticmethod
                def add(a): pass
                @staticmethod
                async def get_by_id(aid): return None
                @staticmethod
                async def list_for_owner(oid): return []
                @staticmethod
                async def delete(aid): pass
            async def commit(self): pass

        return MultimodalService(
            uow=DummyUoW(),
            storage=None,
            ocr_provider=None,
            observability_service=obs
        )

    async def test_emit_attachment_telemetry_success(self):
        obs = CapturingObservabilityService()
        mm = self._make_mm(obs)
        await mm._emit_attachment_telemetry("owner1", "success", 1024)
        types = [e["event_type"] for e in obs.events]
        assert "multimodal.attachment" in types
        evt = obs.events[0]
        assert evt["severity"] == "INFO"
        assert evt["metadata"]["size_bytes"] == 1024

    async def test_emit_attachment_failure_severity(self):
        obs = CapturingObservabilityService()
        mm = self._make_mm(obs)
        await mm._emit_attachment_telemetry("owner1", "failed", 0, error_type="UploadError")
        evt = obs.events[0]
        assert evt["severity"] == "ERROR"

    async def test_multimodal_works_without_observability_service(self):
        mm = self._make_mm(obs=None)
        await mm._emit_attachment_telemetry("owner1", "success", 512)

    async def test_attachment_success_status_in_telemetry(self):
        obs = CapturingObservabilityService()
        mm = self._make_mm(obs)
        await mm._emit_attachment_telemetry("owner1", "success", 2048)
        assert obs.events[0]["status"] == "success"


@pytest.mark.asyncio
class TestObservabilityAPI:
    async def _get_token(self, client):
        r = await client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        return r.json()["access_token"]

    async def test_health_endpoint_is_public(self, async_client):
        r = await async_client.get("/api/v1/observability/health")
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert "liveness" in body
        assert "readiness" in body
        assert "dependencies" in body

    async def test_health_returns_dependency_info(self, async_client):
        r = await async_client.get("/api/v1/observability/health")
        assert r.status_code == 200
        deps = r.json()["dependencies"]
        assert "database" in deps

    async def test_metrics_requires_auth(self, async_client):
        r = await async_client.get("/api/v1/observability/metrics")
        assert r.status_code in (401, 403)

    async def test_metrics_authenticated(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/metrics",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert "counters" in body
        assert "gauges" in body

    async def test_events_requires_auth(self, async_client):
        r = await async_client.get("/api/v1/observability/events")
        assert r.status_code in (401, 403)

    async def test_events_list_authenticated(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_events_filter_by_component(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events?component=model_gateway",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    async def test_events_limit_enforced(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events?limit=5",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) <= 5

    async def test_events_limit_over_max_rejected(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events?limit=9999",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422

    async def test_event_by_id_not_found(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events/non-existent-id-xyz",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    async def test_cleanup_requires_admin(self, async_client):
        await async_client.post("/api/v1/auth/register",
                                json={"username": "obs_user_10", "password": "password123"})
        r = await async_client.post("/api/v1/auth/login",
                                    data={"username": "obs_user_10", "password": "password123"})
        token = r.json()["access_token"]
        cleanup_resp = await async_client.post("/api/v1/observability/cleanup",
                                               headers={"Authorization": f"Bearer {token}"})
        assert cleanup_resp.status_code == 403

    async def test_cleanup_as_admin(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.post("/api/v1/observability/cleanup?max_age_days=60&max_rows=1000",
                                    headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    async def test_request_id_header_echoed(self, async_client):
        r = await async_client.get("/api/v1/observability/health",
                                   headers={"X-Request-ID": "test-req-123"})
        assert r.headers.get("X-Request-ID") == "test-req-123"

    async def test_correlation_id_header_echoed(self, async_client):
        r = await async_client.get("/api/v1/observability/health",
                                   headers={"X-Correlation-ID": "corr-456"})
        assert r.headers.get("X-Correlation-ID") == "corr-456"

    async def test_events_offset_parameter(self, async_client):
        token = await self._get_token(async_client)
        r = await async_client.get("/api/v1/observability/events?offset=0&limit=10",
                                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    async def test_user_isolation_cannot_see_other_user_events(self, async_client):
        # Register user A and user B
        await async_client.post("/api/v1/auth/register", json={"username": "user_iso_a", "password": "password123"})
        await async_client.post("/api/v1/auth/register", json={"username": "user_iso_b", "password": "password123"})
        token_a = (await async_client.post("/api/v1/auth/login", data={"username": "user_iso_a", "password": "password123"})).json()["access_token"]
        token_b = (await async_client.post("/api/v1/auth/login", data={"username": "user_iso_b", "password": "password123"})).json()["access_token"]
        admin_token = await self._get_token(async_client)

        from app.core.observability.service import get_observability_service
        from app.core.observability.schemas import TelemetryEventCreate
        svc = get_observability_service()
        me_a = (await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})).json()
        event_id = await svc.emit_event(TelemetryEventCreate(
            event_type="agent.run.completed",
            component="agent",
            user_id=me_a["id"],
            status="success"
        ))

        # User A can view their event
        r_a = await async_client.get(f"/api/v1/observability/events/{event_id}", headers={"Authorization": f"Bearer {token_a}"})
        assert r_a.status_code == 200

        # User B cannot view user A's event (user isolation: 404)
        r_b = await async_client.get(f"/api/v1/observability/events/{event_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert r_b.status_code == 404

        # Admin CAN view user A's event
        r_admin = await async_client.get(f"/api/v1/observability/events/{event_id}", headers={"Authorization": f"Bearer {admin_token}"})
        assert r_admin.status_code == 200


class TestRetentionAndInterface:
    def test_cleanup_retention_interface_exists(self):
        from app.core.observability.service import IObservabilityService
        assert hasattr(IObservabilityService, "cleanup_retention")

    def test_iobservability_has_all_required_methods(self):
        from app.core.observability.service import IObservabilityService
        for method in ("emit_event", "record_metric", "get_events", "get_event_by_id",
                       "get_metrics", "get_health", "cleanup_retention"):
            assert hasattr(IObservabilityService, method), f"Missing IObservabilityService.{method}"

    def test_observability_service_implements_interface(self):
        from app.core.observability.service import IObservabilityService, ObservabilityService
        assert issubclass(ObservabilityService, IObservabilityService)


class TestHealthStatusSchema:
    def test_health_status_fields(self):
        from app.core.observability.schemas import HealthStatus, DependencyHealth
        from datetime import datetime, timezone
        h = HealthStatus(
            status="healthy", liveness=True, readiness=True,
            timestamp=datetime.now(timezone.utc),
            dependencies={"db": DependencyHealth(status="healthy", latency_ms=1.5)}
        )
        assert h.status == "healthy"
        assert h.liveness is True
        assert h.readiness is True
        assert "db" in h.dependencies

    def test_degraded_health_status(self):
        from app.core.observability.schemas import HealthStatus, DependencyHealth
        from datetime import datetime, timezone
        h = HealthStatus(
            status="degraded", liveness=True, readiness=False,
            timestamp=datetime.now(timezone.utc),
            dependencies={"db": DependencyHealth(status="unhealthy", details={"error": "timeout"})}
        )
        assert h.readiness is False
        assert h.dependencies["db"].status == "unhealthy"

    def test_empty_dependencies_allowed(self):
        from app.core.observability.schemas import HealthStatus
        from datetime import datetime, timezone
        h = HealthStatus(status="healthy", liveness=True, readiness=True,
                        timestamp=datetime.now(timezone.utc))
        assert h.dependencies == {}


@pytest.mark.asyncio
class TestNonBlockingContract:
    async def test_capturing_service_never_raises(self):
        from app.core.observability.schemas import TelemetryEventCreate
        obs = CapturingObservabilityService()
        for i in range(10):
            evt = TelemetryEventCreate(event_type=f"test.event.{i}", component="test")
            result = await obs.emit_event(evt)
            assert result is not None
        assert len(obs.events) == 10

    async def test_db_unavailable_does_not_crash_caller(self):
        from app.core.observability.service import ObservabilityService
        from app.core.observability.schemas import TelemetryEventCreate
        from app.core.observability.metrics import MetricsRegistry

        class AlwaysFailUoW:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            class telemetry_events:
                @staticmethod
                def add(*a, **kw): raise RuntimeError("Disk failure")
            async def commit(self): pass

        svc = ObservabilityService(uow=AlwaysFailUoW(), metrics=MetricsRegistry())
        for i in range(5):
            evt = TelemetryEventCreate(event_type=f"ev.{i}", component="test")
            result = await svc.emit_event(evt)
            assert result is None
