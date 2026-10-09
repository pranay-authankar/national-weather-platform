"""
API Router for Admin Weather Report Moderation.
Provides endpoints for verifying, rejecting, and restoring weather reports,
with persistent audit logging and token-based administrative authorization.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import sanitize_error_message
from schemas.moderation import (
    AuditHistoryListResponse,
    ModerationActionRequest,
    ModerationAuditRecord,
    ModerationResponse,
)
from services.admin_auth_service import get_current_moderator
from services.moderation_service import (
    DuplicateEventRestrictionError,
    EventNotFoundError,
    InvalidStatusTransitionError,
    ModerationValidationError,
    get_audit_history_list,
    get_event_audit_history,
    moderate_weather_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Report Moderation"])


@router.post(
    "/reports/{event_id}/verify",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Verify Weather Report",
    description="Manually verify a weather report with an explicit administrative reason. Protected by admin token.",
)
async def verify_report(
    event_id: str,
    request: ModerationActionRequest,
    moderator_id: str = Depends(get_current_moderator),
) -> ModerationResponse:
    """
    Transition a report to 'Verified':
    - Requires an explicit justification reason.
    - Prevents verifying duplicate records.
    - Preserves existing credibility and duplicate relationships.
    - Records audit log entry.
    """
    try:
        result = moderate_weather_event(
            event_id=event_id,
            new_status="Verified",
            reason=request.reason,
            moderator_id=moderator_id,
        )
        return ModerationResponse(
            event_id=result["event_id"],
            previous_status=result["previous_status"],
            new_status=result["new_status"],
            reason=result["reason"],
            moderator_id=result["moderator_id"],
            moderated_at=result["moderated_at"],
            event=result["event"],
        )
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (InvalidStatusTransitionError, DuplicateEventRestrictionError, ModerationValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=sanitized)


@router.post(
    "/reports/{event_id}/reject",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Reject Weather Report",
    description="Manually reject a weather report with an explicit administrative reason. Protected by admin token.",
)
async def reject_report(
    event_id: str,
    request: ModerationActionRequest,
    moderator_id: str = Depends(get_current_moderator),
) -> ModerationResponse:
    """
    Transition a report to 'Rejected':
    - Requires an explicit justification reason.
    - Updates verification status to 'Rejected' and confidence score to 0.0.
    - Preserves all other event fields.
    - Records audit log entry.
    """
    try:
        result = moderate_weather_event(
            event_id=event_id,
            new_status="Rejected",
            reason=request.reason,
            moderator_id=moderator_id,
        )
        return ModerationResponse(
            event_id=result["event_id"],
            previous_status=result["previous_status"],
            new_status=result["new_status"],
            reason=result["reason"],
            moderator_id=result["moderator_id"],
            moderated_at=result["moderated_at"],
            event=result["event"],
        )
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (InvalidStatusTransitionError, ModerationValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=sanitized)


@router.post(
    "/reports/{event_id}/restore",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Restore Rejected Report",
    description="Restore a previously rejected report to 'Unverified' for reassessment. Protected by admin token.",
)
async def restore_report(
    event_id: str,
    request: ModerationActionRequest,
    moderator_id: str = Depends(get_current_moderator),
) -> ModerationResponse:
    """
    Restore a Rejected report back to 'Unverified' for reassessment:
    - Requires an explicit justification reason.
    - Only valid for events currently in 'Rejected' status.
    - Records audit log entry.
    """
    try:
        result = moderate_weather_event(
            event_id=event_id,
            new_status="Unverified",
            reason=request.reason,
            moderator_id=moderator_id,
        )
        return ModerationResponse(
            event_id=result["event_id"],
            previous_status=result["previous_status"],
            new_status=result["new_status"],
            reason=result["reason"],
            moderator_id=result["moderator_id"],
            moderated_at=result["moderated_at"],
            event=result["event"],
        )
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (InvalidStatusTransitionError, ModerationValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=sanitized)


@router.get(
    "/reports/{event_id}/audit-history",
    response_model=List[ModerationAuditRecord],
    status_code=status.HTTP_200_OK,
    summary="Get Report Audit History",
    description="Retrieve chronological moderation audit log for a specific event. Protected by admin token.",
)
async def get_report_audit_log(
    event_id: str,
    moderator_id: str = Depends(get_current_moderator),
) -> List[ModerationAuditRecord]:
    """
    Get moderation audit trail for an event ordered by timestamp descending.
    """
    try:
        entries = get_event_audit_history(event_id)
        return [ModerationAuditRecord(**e) for e in entries]
    except EventNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ModerationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=sanitized)


@router.get(
    "/audit-history",
    response_model=AuditHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Moderation Audit History",
    description="Retrieve paginated moderation audit history across reports. Protected by admin token.",
)
async def list_audit_history(
    event_id: Optional[str] = Query(None, description="Optional filter by event ID."),
    limit: int = Query(50, ge=1, le=500, description="Page limit."),
    offset: int = Query(0, ge=0, description="Page offset."),
    moderator_id: str = Depends(get_current_moderator),
) -> AuditHistoryListResponse:
    """
    Query all moderation audit records with pagination.
    """
    try:
        result = get_audit_history_list(event_id=event_id, limit=limit, offset=offset)
        return AuditHistoryListResponse(
            data=[ModerationAuditRecord(**r) for r in result["data"]],
            total=result["total"],
            limit=result["limit"],
            offset=result["offset"],
        )
    except ModerationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=sanitized)
