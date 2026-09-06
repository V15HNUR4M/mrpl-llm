from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user
from app.db.models import User
from app.core.observability.schemas import (
    TelemetryEventResponse, HealthStatus
)
from app.core.observability.service import (
    IObservabilityService, get_observability_service
)

router = APIRouter()

def get_service() -> IObservabilityService:
    return get_observability_service()

@router.get("/health", response_model=HealthStatus)
async def get_health_status(
    service: IObservabilityService = Depends(get_service)
):
    """Public/system health endpoint for liveness and readiness probes."""
    return await service.get_health()

@router.get("/metrics", response_model=Dict[str, Any])
async def get_metrics(
    current_user: User = Depends(get_current_user),
    service: IObservabilityService = Depends(get_service)
):
    """Retrieve operational metrics scoped to user/system."""
    is_admin = (current_user.role == "ADMIN")
    target_user_id = None if is_admin else current_user.id
    return await service.get_metrics(user_id=target_user_id, is_admin=is_admin)

@router.get("/events", response_model=List[TelemetryEventResponse])
async def list_telemetry_events(
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    component: Optional[str] = Query(None, description="Filter by component name"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    service: IObservabilityService = Depends(get_service)
):
    """List structured telemetry events with enforced user isolation."""
    is_admin = (current_user.role == "ADMIN")
    target_user_id = user_id if is_admin else current_user.id
    events = await service.get_events(
        user_id=target_user_id,
        is_admin=is_admin,
        component=component,
        event_type=event_type,
        correlation_id=correlation_id,
        status=status_filter,
        limit=limit,
        offset=offset
    )
    return events

@router.get("/events/{event_id}", response_model=TelemetryEventResponse)
async def get_telemetry_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    service: IObservabilityService = Depends(get_service)
):
    """Retrieve a single event respecting user isolation."""
    is_admin = (current_user.role == "ADMIN")
    target_user_id = None if is_admin else current_user.id
    event = await service.get_event_by_id(
        event_id=event_id,
        user_id=target_user_id,
        is_admin=is_admin
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telemetry event not found"
        )
    return event

@router.post("/cleanup", response_model=Dict[str, Any])
async def trigger_retention_cleanup(
    max_age_days: int = Query(30, ge=1),
    max_rows: int = Query(50000, ge=100),
    current_user: User = Depends(get_current_user),
    service: IObservabilityService = Depends(get_service)
):
    """Administrative cleanup of historical telemetry based on retention limits."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    deleted_count = await service.cleanup_retention(max_age_days=max_age_days, max_rows=max_rows)
    return {"status": "success", "deleted_events": deleted_count}
