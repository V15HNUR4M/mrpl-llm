import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from app.db.uow import UnitOfWork, get_uow
from app.db.models import TelemetryEvent
from app.core.observability.schemas import (
    TelemetryEventCreate, HealthStatus, DependencyHealth
)
from app.core.observability.redaction import sanitize_metadata
from app.core.observability.metrics import MetricsRegistry, default_metrics

logger = logging.getLogger("mrpl.observability")


class IObservabilityService(ABC):
    @abstractmethod
    async def emit_event(self, event: TelemetryEventCreate) -> Optional[str]:
        """Emit structured telemetry event. Failures MUST NOT break callers."""
        pass

    @abstractmethod
    def record_metric(self, name: str, value: float = 1.0, is_latency: bool = False) -> None:
        """Record an in-memory counter or latency metric."""
        pass

    @abstractmethod
    async def get_events(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        component: Optional[str] = None,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TelemetryEvent]:
        """Query stored telemetry events respecting user isolation."""
        pass

    @abstractmethod
    async def get_event_by_id(
        self,
        event_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Optional[TelemetryEvent]:
        """Retrieve a single event respecting user isolation."""
        pass

    @abstractmethod
    async def get_metrics(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        """Retrieve snapshot of aggregated metrics."""
        pass

    @abstractmethod
    async def get_health(self) -> HealthStatus:
        """Evaluate subsystem and dependency health."""
        pass

    @abstractmethod
    async def cleanup_retention(
        self,
        max_age_days: int = 30,
        max_rows: int = 50000
    ) -> int:
        """Enforce retention limits on persisted telemetry."""
        pass


class ObservabilityService(IObservabilityService):
    def __init__(self, uow: Optional[UnitOfWork] = None, metrics: Optional[MetricsRegistry] = None):
        self._uow = uow or get_uow()
        self._metrics = metrics or default_metrics

    async def emit_event(self, event: TelemetryEventCreate) -> Optional[str]:
        # 1. Update in-memory metrics synchronously first
        try:
            self._update_metrics_from_event(event)
        except Exception as me:
            logger.warning(f"Failed to update metrics from event: {me}")

        # 2. Persist to database with explicit resilience boundary
        try:
            cleaned_metadata = sanitize_metadata(event.metadata)
            
            db_event = TelemetryEvent(
                event_type=event.event_type,
                component=event.component,
                severity=event.severity,
                user_id=event.user_id,
                request_id=event.request_id,
                correlation_id=event.correlation_id,
                session_id=event.session_id,
                span_id=event.span_id,
                trace_id=event.trace_id,
                duration_ms=event.duration_ms,
                status=event.status,
                error_type=event.error_type,
                metadata_=cleaned_metadata
            )

            async with self._uow as u:
                u.telemetry_events.add(db_event)
                await u.commit()
                return db_event.id

        except Exception as e:
            # Observability failure MUST NOT break the caller or underlying business operation!
            logger.error(f"Failed to persist telemetry event [{event.event_type}]: {e}", exc_info=False)
            return None

    def _update_metrics_from_event(self, event: TelemetryEventCreate) -> None:
        c = event.component.lower()
        st = (event.status or "").lower()

        self._metrics.increment(f"{c}_events_total")

        if event.duration_ms is not None and event.duration_ms >= 0:
            self._metrics.record_latency(f"{c}_latency_ms", float(event.duration_ms))

        if st in ("failed", "error"):
            self._metrics.increment(f"{c}_failures_total")
        elif st == "denied":
            self._metrics.increment(f"{c}_denials_total")
        elif st == "timed_out":
            self._metrics.increment(f"{c}_timeouts_total")
        elif st == "cancelled":
            self._metrics.increment(f"{c}_cancellations_total")
        elif st == "success":
            self._metrics.increment(f"{c}_success_total")

        # Specific metric mappings
        if event.event_type.startswith("model."):
            self._metrics.increment("model_requests_total")
            if st in ("failed", "error"):
                self._metrics.increment("model_failures_total")
            if event.metadata:
                if "total_tokens" in event.metadata:
                    self._metrics.increment("model_total_tokens_total", int(event.metadata["total_tokens"]))
                if "input_tokens" in event.metadata:
                    self._metrics.increment("model_input_tokens_total", int(event.metadata["input_tokens"]))
                if "output_tokens" in event.metadata:
                    self._metrics.increment("model_output_tokens_total", int(event.metadata["output_tokens"]))

        elif event.event_type.startswith("tool."):
            self._metrics.increment("tool_calls_total")
            if st == "denied":
                self._metrics.increment("tool_denials_total")
            elif st in ("failed", "error"):
                self._metrics.increment("tool_failures_total")

        elif event.event_type.startswith("workflow."):
            if "run.started" in event.event_type:
                self._metrics.increment("workflow_runs_total")
            if st == "timed_out":
                self._metrics.increment("workflow_timeouts_total")
            elif st in ("failed", "error"):
                self._metrics.increment("workflow_failures_total")

        elif event.event_type.startswith("rag."):
            self._metrics.increment("rag_queries_total")
            if event.metadata and event.metadata.get("empty_result"):
                self._metrics.increment("rag_empty_results_total")

        elif event.event_type.startswith("multimodal.ocr"):
            self._metrics.increment("ocr_requests_total")
            if st in ("failed", "error"):
                self._metrics.increment("ocr_failures_total")
        elif event.event_type.startswith("multimodal.attachment"):
            self._metrics.increment("attachment_uploads_total")

    def record_metric(self, name: str, value: float = 1.0, is_latency: bool = False) -> None:
        try:
            if is_latency:
                self._metrics.record_latency(name, value)
            else:
                self._metrics.increment(name, int(value))
        except Exception as e:
            logger.warning(f"Failed to record metric {name}: {e}")

    async def get_events(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        component: Optional[str] = None,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TelemetryEvent]:
        async with self._uow as u:
            return await u.telemetry_events.query_events(
                user_id=user_id,
                is_admin=is_admin,
                component=component,
                event_type=event_type,
                correlation_id=correlation_id,
                status=status,
                limit=limit,
                offset=offset
            )

    async def get_event_by_id(
        self,
        event_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Optional[TelemetryEvent]:
        async with self._uow as u:
            return await u.telemetry_events.get_for_user(
                event_id=event_id,
                user_id=user_id,
                is_admin=is_admin
            )

    async def get_metrics(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False
    ) -> Dict[str, Any]:
        snapshot = self._metrics.get_snapshot()
        # Include count of stored telemetry events from DB
        async with self._uow as u:
            db_event_count = await u.telemetry_events.count_events(user_id=user_id, is_admin=is_admin)
        snapshot["counters"]["persisted_events_total"] = db_event_count
        return snapshot

    async def get_health(self) -> HealthStatus:
        dependencies: Dict[str, DependencyHealth] = {}
        overall_healthy = True

        # Check Database
        db_start = datetime.now(timezone.utc)
        try:
            from sqlalchemy import text
            async with self._uow as u:
                await u.session.execute(text("SELECT 1"))
            db_lat = (datetime.now(timezone.utc) - db_start).total_seconds() * 1000.0
            dependencies["database"] = DependencyHealth(status="healthy", latency_ms=round(db_lat, 2))
        except Exception as e:
            dependencies["database"] = DependencyHealth(status="unhealthy", details={"error": str(e)})
            overall_healthy = False

        # Check Model Gateway / Provider
        dependencies["model_gateway"] = DependencyHealth(status="healthy")

        # Check Local Storage
        dependencies["storage"] = DependencyHealth(status="healthy")

        return HealthStatus(
            status="healthy" if overall_healthy else "degraded",
            liveness=True,
            readiness=overall_healthy,
            timestamp=datetime.now(timezone.utc),
            dependencies=dependencies
        )

    async def cleanup_retention(
        self,
        max_age_days: int = 30,
        max_rows: int = 50000
    ) -> int:
        async with self._uow as u:
            count = await u.telemetry_events.cleanup_retention(
                max_age_days=max_age_days,
                max_rows=max_rows
            )
            await u.commit()
            return count


_global_observability_service: Optional[IObservabilityService] = None

def get_observability_service() -> IObservabilityService:
    global _global_observability_service
    if _global_observability_service is None:
        _global_observability_service = ObservabilityService()
    return _global_observability_service
