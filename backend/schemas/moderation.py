"""
Pydantic schemas for Admin Weather Report Moderation API.
Defines data structures for moderation actions, audit records, and paginated audit histories.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ModerationActionRequest(BaseModel):
    """
    Payload required for admin moderation actions (verify, reject, restore).
    Requires an explicit justification reason.
    """
    reason: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Explicit administrative justification for this moderation decision.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_not_whitespace(cls, val: str) -> str:
        cleaned = val.strip()
        if len(cleaned) < 3:
            raise ValueError("Moderation reason must be at least 3 characters long and cannot be only whitespace.")
        return cleaned


class ModerationAuditRecord(BaseModel):
    """
    Representation of an audit log entry for a moderation action.
    """
    audit_id: str = Field(..., description="Unique UUID for this audit log entry.")
    event_id: str = Field(..., description="Target weather event UUID.")
    previous_status: str = Field(..., description="Verification status prior to this moderation action.")
    new_status: str = Field(..., description="Verification status resulting from this moderation action.")
    reason: str = Field(..., description="Administrative justification provided by moderator.")
    moderator_id: str = Field(..., description="Authenticated administrative identity.")
    created_at: str = Field(..., description="ISO-8601 timestamp when moderation occurred.")


class ModerationResponse(BaseModel):
    """
    Response returned upon successfully executing a moderation action.
    """
    event_id: str = Field(..., description="Moderated event UUID.")
    previous_status: str = Field(..., description="Status before moderation.")
    new_status: str = Field(..., description="Status after moderation.")
    reason: str = Field(..., description="Moderation reason recorded in audit log.")
    moderator_id: str = Field(..., description="Authenticated moderator identifier.")
    moderated_at: str = Field(..., description="ISO-8601 timestamp of moderation decision.")
    event: Dict[str, Any] = Field(..., description="Full updated weather event representation.")


class AuditHistoryListResponse(BaseModel):
    """
    Paginated audit history records response.
    """
    data: List[ModerationAuditRecord] = Field(..., description="List of audit log records.")
    total: int = Field(..., description="Total audit records matching query.")
    limit: int = Field(..., description="Page limit requested.")
    offset: int = Field(..., description="Page offset requested.")
