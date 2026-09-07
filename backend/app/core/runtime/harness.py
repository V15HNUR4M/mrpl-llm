import asyncio
import uuid
import re
from typing import Dict, Any, List, Optional, AsyncGenerator
import json

from app.core.agent.registry import AgentRegistry, AgentDefinition
from app.core.runtime.schemas import (
    RuntimeSession, ExecutionState, ExecutionEvent, ToolRequest, AgentDecision
)
from app.core.runtime.errors import (
    IterationLimitExceeded, ToolCallLimitExceeded, ExecutionCancelled, ExecutionTimeout
)
from app.core.runtime.tool_executor import ToolExecutor
from app.core.context_engine.engine import ContextEngine
from app.core.context_engine.schemas import ContextCandidate
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.schemas import GenerationRequest

class AgentHarness:
    def __init__(self, registry: AgentRegistry, context_engine: ContextEngine, model_gateway: ModelGateway, tool_executor: ToolExecutor, observability_service=None):
        self.registry = registry
        self.context_engine = context_engine
        self.gateway = model_gateway
        self.tool_executor = tool_executor
        self.observability_service = observability_service

    def _check_limits(self, session: RuntimeSession, agent: AgentDefinition):
        if session.iteration_count >= agent.execution_limits.max_steps:
            session.transition_to(ExecutionState.LIMIT_REACHED)
            raise IterationLimitExceeded(agent.execution_limits.max_steps)
        session.iteration_count += 1

    def _prepare_context(self, session: RuntimeSession, candidates: List[ContextCandidate]):
        session.transition_to(ExecutionState.CONTEXT_BUILDING)
        package = self.context_engine.assemble_context(candidates)
        session.add_event("context_assembled", {"token_budget": package.token_budget})
        return package

    async def _perform_rag_retrieval(
        self,
        session: RuntimeSession,
        agent: AgentDefinition,
        query: str,
        candidates: List[ContextCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Invokes search_documents tool via self.tool_executor according to canonical architecture:
        Agent Harness -> Tool Registry -> AuthorizationPolicy -> AuthorizedToolExecutor -> search_documents -> ContextCandidate.
        Tracks executed queries to avoid redundant duplicate retrieval.
        Returns citation/metadata events for streaming/visibility without full raw chunk text.
        """
        if not self.tool_executor:
            return []
        if not (getattr(agent.context_policy, "rag", False) or "search_documents" in (agent.tool_permissions.allowed or [])):
            return []
        executed = session.metadata.setdefault("executed_rag_queries", [])
        norm_query = query.strip().lower()
        if not norm_query or norm_query in executed:
            return []
        executed.append(norm_query)

        tool_req = ToolRequest(
            tool="search_documents",
            arguments={"query": query},
            call_id=str(uuid.uuid4())
        )

        allowed = agent.tool_permissions.allowed if agent.tool_permissions.allowed else ["search_documents"]
        try:
            tool_result = await self.tool_executor.execute(
                tool_req,
                context={
                    "session_id": session.session_id,
                    "agent_id": agent.agent_id,
                    "user_id": session.user_id
                },
                allowed_tools=allowed
            )
        except Exception:
            return []

        events = []
        if tool_result.context_candidates:
            candidates.extend(tool_result.context_candidates)
            for c in tool_result.context_candidates:
                meta = c.metadata.copy()
                meta["filename"] = c.source or meta.get("filename", "Document")
                events.append({
                    "type": "context_candidate",
                    "candidate": {
                        "id": c.id,
                        "type": "rag",
                        "source": c.source or "search_documents",
                        "relevance_score": c.relevance_score,
                        "metadata": meta
                    }
                })
        return events

    async def _execute_tools(self, session: RuntimeSession, agent: AgentDefinition, decision: AgentDecision, candidates: List[ContextCandidate]):
        session.transition_to(ExecutionState.WAITING_FOR_TOOL)
        
        events = []
        for tool_req in decision.tool_requests:
            if session.tool_call_count >= agent.execution_limits.max_tool_calls:
                session.transition_to(ExecutionState.LIMIT_REACHED)
                raise ToolCallLimitExceeded(agent.execution_limits.max_tool_calls)
            
            # Check for duplicate identical RAG retrieval (Requirement 4)
            if tool_req.tool == "search_documents":
                q_text = str(tool_req.arguments.get("query", "")).strip().lower()
                executed = session.metadata.setdefault("executed_rag_queries", [])
                if q_text in executed:
                    events.append({
                        "type": "tool_completed",
                        "tool": tool_req.tool,
                        "result": "Query already executed in current session; skipped duplicate retrieval.",
                        "status": "skipped"
                    })
                    continue
                executed.append(q_text)

            session.tool_call_count += 1
            session.transition_to(ExecutionState.TOOL_EXECUTION)
            events.append({"type": "tool_execution_started", "tool": tool_req.tool, "arguments": tool_req.arguments})
            
            try:
                tool_result = await self.tool_executor.execute(
                    tool_req, 
                    context={
                        "session_id": session.session_id,
                        "agent_id": agent.agent_id,
                        "user_id": session.user_id,
                        "conversation_id": session.conversation_id
                    }
                )
                
                if tool_result.status == "error":
                    result_str = json.dumps({"status": "error", "message": tool_result.output})
                else:
                    result_str = json.dumps(tool_result.output)
                    
                session.add_event("tool_completed", {"tool": tool_req.tool, "call_id": tool_req.call_id, "result": tool_result.output})
                
                candidates.append(ContextCandidate(
                    id=tool_req.call_id, type="tool", content=result_str, source=tool_req.tool, priority=4
                ))
                
                events.append({"type": "tool_completed", "tool": tool_req.tool, "result": tool_result.output, "status": tool_result.status})
                
                if tool_result.context_candidates:
                    candidates.extend(tool_result.context_candidates)
                    for c in tool_result.context_candidates:
                        events.append({"type": "context_candidate", "candidate": c.model_dump()})
                    
            except Exception as e:
                result_str = json.dumps({"status": "error", "message": str(e)})
                session.add_event("tool_completed", {"tool": tool_req.tool, "call_id": tool_req.call_id})
                candidates.append(ContextCandidate(
                    id=tool_req.call_id, type="tool", content=result_str, source=tool_req.tool, priority=4
                ))
                events.append({"type": "tool_completed", "tool": tool_req.tool, "result": str(e), "status": "error"})
                
        session.transition_to(ExecutionState.RUNNING)
        return events

    async def _emit_telemetry(self, event_type: str, session: RuntimeSession, status: str, duration_ms: int = None, error_type: str = None, metadata: dict = None):
        if not self.observability_service:
            return
        try:
            from app.core.observability.schemas import TelemetryEventCreate
            severity = "ERROR" if status in ("failed", "error", "timed_out") else "INFO"
            meta = {"agent_id": session.agent_id}
            if metadata:
                meta.update(metadata)
            event = TelemetryEventCreate(
                event_type=event_type,
                component="agent",
                severity=severity,
                user_id=session.user_id or None,
                session_id=session.session_id,
                duration_ms=duration_ms,
                status=status,
                error_type=error_type,
                metadata=meta
            )
            await self.observability_service.emit_event(event)
        except Exception:
            # Observability failures MUST NOT break agent execution
            pass

    async def execute(self, session: RuntimeSession, user_input: str, additional_candidates: List[ContextCandidate] = None) -> AgentDecision:
        import time
        t0 = time.time()
        agent = self.registry.get(session.agent_id)
        await self._emit_telemetry("agent.run.started", session, status="started")
        
        try:
            session.transition_to(ExecutionState.INITIALIZING)
            loop = asyncio.get_running_loop()
            timeout_task = loop.create_task(asyncio.sleep(agent.execution_limits.timeout_seconds))
            exec_task = loop.create_task(self._execution_loop(session, agent, user_input, additional_candidates))
            
            done, pending = await asyncio.wait([timeout_task, exec_task], return_when=asyncio.FIRST_COMPLETED)
            
            if timeout_task in done and not exec_task.done():
                exec_task.cancel()
                session.transition_to(ExecutionState.TIMED_OUT)
                dur = int((time.time() - t0) * 1000)
                await self._emit_telemetry("agent.run.timeout", session, status="timed_out", duration_ms=dur, error_type="ExecutionTimeout")
                raise ExecutionTimeout(agent.execution_limits.timeout_seconds)
                
            if exec_task in done:
                timeout_task.cancel()
                dur = int((time.time() - t0) * 1000)
                await self._emit_telemetry("agent.run.completed", session, status="success", duration_ms=dur)
                return exec_task.result()
                
        except asyncio.CancelledError:
            session.transition_to(ExecutionState.CANCELLING)
            session.transition_to(ExecutionState.CANCELLED)
            dur = int((time.time() - t0) * 1000)
            await self._emit_telemetry("agent.run.failed", session, status="cancelled", duration_ms=dur)
            raise ExecutionCancelled()
        except (ExecutionTimeout,):
            raise
        except Exception as e:
            if session.state not in (ExecutionState.COMPLETED, ExecutionState.CANCELLED, ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED):
                session.transition_to(ExecutionState.FAILED)
            dur = int((time.time() - t0) * 1000)
            await self._emit_telemetry("agent.run.failed", session, status="failed", duration_ms=dur, error_type=type(e).__name__)
            raise

    async def _execution_loop(self, session: RuntimeSession, agent: AgentDefinition, initial_input: str, additional_candidates: List[ContextCandidate] = None) -> AgentDecision:
        session.transition_to(ExecutionState.RUNNING)
        
        candidates: List[ContextCandidate] = [
            ContextCandidate(id="sys", type="system", content=agent.instructions, priority=1),
            ContextCandidate(id="req", type="request", content=initial_input, priority=2)
        ]
        
        if additional_candidates:
            candidates.extend(additional_candidates)

        # Trigger automatic initial RAG retrieval if configured
        await self._perform_rag_retrieval(session, agent, initial_input, candidates)

        step_idx = 0
        while True:
            self._check_limits(session, agent)
            package = self._prepare_context(session, candidates)
            
            session.transition_to(ExecutionState.GENERATING)
            step_idx += 1
            await self._emit_telemetry("agent.step.started", session, status="started", metadata={"step": step_idx})
            
            from app.core.config import settings
            gen_req = self.context_engine.convert_to_generation_request(package, settings.DEFAULT_CHAT_MODEL)
            gen_req.metadata["user_id"] = session.user_id
            gen_req.metadata["session_id"] = session.session_id
            gen_req.metadata["correlation_id"] = session.metadata.get("correlation_id", session.session_id)
            
            response = await self.gateway.generate(gen_req)
            session.add_event("model_generation_completed", {"usage": response.usage.model_dump()})
            
            session.transition_to(ExecutionState.PROCESSING_RESULT)
            decision = self._parse_decision(response, agent=agent, user_input=initial_input, session=session)
            await self._emit_telemetry("agent.step.completed", session, status="success", metadata={"step": step_idx})
            
            candidates.append(ContextCandidate(
                id=str(uuid.uuid4()), type="message", content=response.text, metadata={"role": "assistant"}, priority=5
            ))
            
            if decision.final_answer or not decision.tool_requests:
                session.transition_to(ExecutionState.COMPLETED)
                if not decision.final_answer:
                    decision.final_answer = response.text
                return decision
                
            await self._execute_tools(session, agent, decision, candidates)

    async def stream_execute(self, session: RuntimeSession, user_input: str, additional_candidates: List[ContextCandidate] = None) -> AsyncGenerator[Dict[str, Any], None]:
        agent = self.registry.get(session.agent_id)
        
        try:
            session.transition_to(ExecutionState.INITIALIZING)
            async with asyncio.timeout(agent.execution_limits.timeout_seconds):
                async for event in self._stream_execution_loop(session, agent, user_input, additional_candidates):
                    yield event
                    
        except asyncio.TimeoutError:
            session.transition_to(ExecutionState.TIMED_OUT)
            yield {"type": "error", "error": "ExecutionTimeout"}
        except asyncio.CancelledError:
            session.transition_to(ExecutionState.CANCELLING)
            session.transition_to(ExecutionState.CANCELLED)
            yield {"type": "error", "error": "ExecutionCancelled"}
        except Exception as e:
            if session.state not in (ExecutionState.COMPLETED, ExecutionState.CANCELLED, ExecutionState.TIMED_OUT, ExecutionState.LIMIT_REACHED):
                session.transition_to(ExecutionState.FAILED)
            yield {"type": "error", "error": str(e)}

    async def _stream_execution_loop(self, session: RuntimeSession, agent: AgentDefinition, initial_input: str, additional_candidates: List[ContextCandidate] = None) -> AsyncGenerator[Dict[str, Any], None]:
        session.transition_to(ExecutionState.RUNNING)
        yield {"type": "state_changed", "state": session.state.value}
        
        candidates: List[ContextCandidate] = [
            ContextCandidate(id="sys", type="system", content=agent.instructions, priority=1),
            ContextCandidate(id="req", type="request", content=initial_input, priority=2)
        ]
        
        if additional_candidates:
            candidates.extend(additional_candidates)

        # Trigger automatic initial RAG retrieval if configured
        rag_events = await self._perform_rag_retrieval(session, agent, initial_input, candidates)
        for rev in rag_events:
            yield rev

        while True:
            self._check_limits(session, agent)
            
            package = self._prepare_context(session, candidates)
            yield {"type": "state_changed", "state": session.state.value}
            
            session.transition_to(ExecutionState.GENERATING)
            yield {"type": "state_changed", "state": session.state.value}
            
            from app.core.config import settings
            gen_req = self.context_engine.convert_to_generation_request(package, settings.DEFAULT_CHAT_MODEL, stream=True)
            gen_req.metadata["user_id"] = session.user_id
            gen_req.metadata["session_id"] = session.session_id
            gen_req.metadata["correlation_id"] = session.metadata.get("correlation_id", session.session_id)
            
            full_text = ""
            async for chunk in self.gateway.stream(gen_req):
                if chunk.type == "text_delta":
                    full_text += chunk.text
                    yield {"type": "text_delta", "text": chunk.text}
                elif chunk.type == "completed":
                    session.add_event("model_generation_completed", {"usage": chunk.usage.model_dump() if chunk.usage else {}})
            
            session.transition_to(ExecutionState.PROCESSING_RESULT)
            yield {"type": "state_changed", "state": session.state.value}
            
            class DummyResponse:
                def __init__(self, text):
                    self.text = text
            decision = self._parse_decision(DummyResponse(full_text), agent=agent, user_input=initial_input, session=session)
            
            candidates.append(ContextCandidate(
                id=str(uuid.uuid4()), type="message", content=full_text, metadata={"role": "assistant"}, priority=5
            ))
            
            if decision.final_answer or not decision.tool_requests:
                session.transition_to(ExecutionState.COMPLETED)
                yield {"type": "state_changed", "state": session.state.value}
                if not decision.final_answer:
                    decision.final_answer = full_text
                yield {"type": "completed", "final_answer": decision.final_answer}
                return
                
            yield {"type": "tool_requests", "requests": [t.model_dump() for t in decision.tool_requests]}
            
            tool_events = await self._execute_tools(session, agent, decision, candidates)
            for event in tool_events:
                yield event
                
            yield {"type": "state_changed", "state": session.state.value}

    def _parse_decision(
        self,
        response: Any,
        agent: Optional[AgentDefinition] = None,
        user_input: Optional[str] = None,
        session: Optional[RuntimeSession] = None
    ) -> AgentDecision:
        """
        Extracts tool calls or final answers using structured provider response,
        JSON action blocks, or Excel Agent spreadsheet-generation workflow.
        """
        # 1. Provider tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_requests = []
            for tc in response.tool_calls:
                tool_requests.append(
                    ToolRequest(
                        tool=tc.function.get("name", ""), 
                        arguments=tc.function.get("arguments", {}), 
                        call_id=tc.id or str(uuid.uuid4())
                    )
                )
            return AgentDecision(tool_requests=tool_requests)

        text = getattr(response, "text", "") or ""
        text_clean = text.strip()

        # 2. Structured JSON tool call blocks in text
        allowed_tools = agent.tool_permissions.allowed if (agent and agent.tool_permissions) else []
        json_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text_clean)
        for block in json_blocks:
            try:
                obj = json.loads(block)
                if isinstance(obj, dict) and ("tool" in obj or "name" in obj):
                    tool_name = obj.get("tool") or obj.get("name")
                    if not allowed_tools or tool_name in allowed_tools:
                        return AgentDecision(tool_requests=[
                            ToolRequest(
                                tool=tool_name,
                                arguments=obj.get("arguments", {}),
                                call_id=str(uuid.uuid4())
                            )
                        ])
            except Exception:
                pass

        # 3. Excel Agent Spreadsheet Generation Workflow Selection
        if agent and agent.agent_id == "excel_agent" and user_input:
            has_already_created = False
            if session:
                has_already_created = any(
                    e.type == "tool_completed" and e.data.get("tool") == "create_workbook"
                    for e in session.events
                )
            if not has_already_created:
                from app.core.runtime.task_router import TaskRouter
                from app.core.excel.table_parser import extract_tabular_data
                from app.services.file_export.file_manager import derive_filename

                is_excel_intent = TaskRouter.should_route_to_excel_agent(user_input) or any(
                    k in user_input.lower() for k in ("create", "generate", "build", "make", "spreadsheet", "workbook", "excel", ".xlsx")
                )
                if is_excel_intent:
                    session_events = [e.model_dump() for e in session.events] if session else None
                    headers, rows = extract_tabular_data(text_clean, session_events=session_events, user_input=user_input)
                    if headers and rows:
                        filename = derive_filename(user_input, ext=".xlsx")
                        return AgentDecision(tool_requests=[
                            ToolRequest(
                                tool="create_workbook",
                                arguments={
                                    "sheet_name": "Data",
                                    "headers": headers,
                                    "rows": rows,
                                    "output_filename": filename
                                },
                                call_id=str(uuid.uuid4())
                            )
                        ])

        return AgentDecision(final_answer=text_clean)
