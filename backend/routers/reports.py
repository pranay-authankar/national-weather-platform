import logging
import os
from pathlib import Path
import re
import uuid
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from database import sanitize_error_message
from schemas.reports import CitizenReportCreate, CitizenReportResponse, MediaUploadResponse
from services.citizen_report_service import process_and_store_citizen_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Citizen Reports"])

# Persistent uploads storage directory
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "video/ogg",
    "video/3gpp",
}


@router.post(
    "/upload",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Media Evidence for Citizen Report",
    description=(
        "Uploads a captured photo or recorded video file to persistent storage. "
        "Validates file type and size limits (10MB for photos, 50MB for videos), "
        "persists the file, and returns accessible URLs for report association."
    ),
)
async def upload_media_file(
    file: UploadFile = File(...),
    request: Request = None,
) -> MediaUploadResponse:
    content_type = (file.content_type or "").lower().split(";")[0].strip()

    is_image = content_type in ALLOWED_IMAGE_TYPES or content_type.startswith("image/")
    is_video = content_type in ALLOWED_VIDEO_TYPES or content_type.startswith("video/")

    if not is_image and not is_video:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported media format '{content_type}'. "
                "Allowed formats: JPEG, PNG, WebP, GIF for photos; MP4, WebM, QuickTime for videos."
            ),
        )

    media_type = "image" if is_image else "video"
    max_size = MAX_IMAGE_SIZE_BYTES if is_image else MAX_VIDEO_SIZE_BYTES
    max_mb = 10 if is_image else 50

    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file content.",
        )

    file_size = len(content)
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded {media_type} exceeds maximum allowed size of {max_mb} MB.",
        )
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Sanitize and extract extension
    raw_ext = Path(file.filename or "").suffix.lower()
    if not raw_ext:
        if "jpeg" in content_type or "jpg" in content_type:
            raw_ext = ".jpg"
        elif "png" in content_type:
            raw_ext = ".png"
        elif "webp" in content_type:
            raw_ext = ".webp"
        elif "mp4" in content_type:
            raw_ext = ".mp4"
        elif "webm" in content_type:
            raw_ext = ".webm"
        else:
            raw_ext = ".bin"

    safe_ext = re.sub(r"[^a-zA-Z0-9.]", "", raw_ext)
    unique_filename = f"{media_type}_{uuid.uuid4().hex[:16]}{safe_ext}"
    target_path = UPLOADS_DIR / unique_filename

    try:
        with open(target_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        logger.error("Failed to write media file to disk: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save media file to persistent storage.",
        )

    relative_url = f"/uploads/{unique_filename}"
    base_url = str(request.base_url).rstrip("/") if request else ""
    full_url = f"{base_url}{relative_url}" if base_url else relative_url

    return MediaUploadResponse(
        url=full_url,
        relative_url=relative_url,
        filename=unique_filename,
        media_type=media_type,
        content_type=content_type,
        size_bytes=file_size,
    )


@router.post(
    "",
    response_model=CitizenReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Citizen Weather Report",
    description=(
        "Allows citizens to submit ground-level weather observations. "
        "Validates coordinates and required fields, reverse-geocodes administrative location "
        "(city, district, state), evaluates spatio-temporal duplicates, deterministically calculates "
        "evidence-based verification and confidence scoring, and stores the report safely in PostgreSQL."
    ),
)
async def submit_citizen_report(report: CitizenReportCreate) -> CitizenReportResponse:
    """
    Handle POST /api/reports:
    - Validates latitude (-90 to 90) and longitude (-180 to 180) via Pydantic.
    - Validates event_type and description are non-empty strings.
    - Reverse geocodes coordinates to automatically determine city, district, and state.
    - Evaluates geographic and temporal duplicate criteria against existing events.
    - Evaluates independent supporting evidence to assign verification_status and confidence_score.
    - Persists report to public.weather_events with source='Citizen_Report'.
    - Returns event_id and status='received'.
    """
    try:
        result = await process_and_store_citizen_report(report)
        return CitizenReportResponse(
            event_id=result["event_id"],
            status=result["status"],
        )
    except RuntimeError as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Database failure while handling citizen report: %s", sanitized_msg)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to store citizen weather report.",
        )
    except Exception as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Unexpected error in submit_citizen_report: %s", sanitized_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the report.",
        )

