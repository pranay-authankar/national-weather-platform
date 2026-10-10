"""
Service module for ElevenLabs Speech-to-Text integration.
Transcribes audio recordings using ElevenLabs' official Speech-to-Text API (model: scribe_v2).
Never leaks API keys or secrets in logs or responses.
"""

import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Set
from dotenv import dotenv_values, load_dotenv
from fastapi import HTTPException, UploadFile, status
import httpx

logger = logging.getLogger(__name__)

# Ensure backend/.env is loaded without overriding environment variables
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)


def sanitize_upstream_error_detail(detail_raw: Any, api_key: str) -> str:
    """
    Sanitize error message from upstream ElevenLabs response.
    Never exposes API keys or raw credentials.
    """
    if isinstance(detail_raw, dict):
        msg = detail_raw.get("message") or detail_raw.get("msg") or str(detail_raw)
    elif isinstance(detail_raw, list):
        parts = []
        for item in detail_raw:
            if isinstance(item, dict):
                parts.append(item.get("msg") or item.get("message") or str(item))
            else:
                parts.append(str(item))
        msg = "; ".join(parts)
    elif isinstance(detail_raw, str):
        msg = detail_raw
    else:
        msg = str(detail_raw) if detail_raw is not None else ""

    if api_key and api_key in msg:
        msg = msg.replace(api_key, "[REDACTED_API_KEY]")

    # Redact any other potential sk_ keys or auth tokens
    msg = re.sub(r"sk_[a-zA-Z0-9_\-]+", "[REDACTED_KEY]", msg)
    return msg.strip()

# ElevenLabs STT Constants & Defaults
DEFAULT_ELEVENLABS_API_URL: str = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_ELEVENLABS_MODEL_ID: str = "scribe_v2"
DEFAULT_MAX_AUDIO_SIZE_MB: float = 25.0
DEFAULT_TIMEOUT_SECONDS: float = 30.0

# Supported audio MIME types and file extensions
SUPPORTED_AUDIO_MIME_TYPES: Set[str] = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
    "audio/x-flac",
    "video/webm",
    "video/mp4",
}

SUPPORTED_AUDIO_EXTENSIONS: Set[str] = {
    ".webm",
    ".ogg",
    ".wav",
    ".mp3",
    ".mp4",
    ".m4a",
    ".aac",
    ".flac",
}


_last_env_mtime: float = 0.0


def get_elevenlabs_config() -> Dict[str, Any]:
    """
    Retrieve ElevenLabs configuration from environment variables.
    Automatically reloads backend/.env if the file was modified on disk,
    while preserving test mocks and process overrides.
    """
    global _last_env_mtime
    if env_path.exists():
        try:
            mtime = env_path.stat().st_mtime
            if mtime > _last_env_mtime:
                _last_env_mtime = mtime
                load_dotenv(dotenv_path=env_path, override=True)
        except Exception:
            pass

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    model_id = os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_ELEVENLABS_MODEL_ID).strip() or DEFAULT_ELEVENLABS_MODEL_ID
    api_url = os.getenv("ELEVENLABS_API_URL", DEFAULT_ELEVENLABS_API_URL).strip() or DEFAULT_ELEVENLABS_API_URL

    try:
        max_size_mb = float(os.getenv("ELEVENLABS_MAX_AUDIO_SIZE_MB", str(DEFAULT_MAX_AUDIO_SIZE_MB)))
    except (TypeError, ValueError):
        max_size_mb = DEFAULT_MAX_AUDIO_SIZE_MB

    try:
        timeout_seconds = float(os.getenv("ELEVENLABS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    return {
        "api_key": api_key,
        "model_id": model_id,
        "api_url": api_url,
        "max_size_mb": max_size_mb,
        "timeout_seconds": timeout_seconds,
    }


def is_supported_audio_format(content_type: Optional[str], filename: Optional[str]) -> bool:
    """
    Check if the MIME type or file extension is among supported audio formats.
    """
    # Normalize MIME type (ignore parameters like ;codecs=opus)
    norm_mime = ""
    if content_type:
        norm_mime = content_type.split(";")[0].strip().lower()

    if norm_mime in SUPPORTED_AUDIO_MIME_TYPES or norm_mime.startswith("audio/"):
        return True

    # Fallback to extension check
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in SUPPORTED_AUDIO_EXTENSIONS:
            return True

    return False


async def transcribe_audio_file(
    file: UploadFile,
    language_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate and transcribe an audio file using ElevenLabs STT API.

    Args:
        file: UploadFile containing recorded audio data.
        language_code: Optional ISO-639 language code for language biasing.

    Returns:
        Dict containing "text" and optional "language_code".

    Raises:
        HTTPException with appropriate status codes (400, 413, 429, 502, 503, 504).
    """
    config = get_elevenlabs_config()
    api_key = config["api_key"]
    model_id = config["model_id"]
    api_url = config["api_url"]
    max_size_mb = config["max_size_mb"]
    timeout_seconds = config["timeout_seconds"]

    # 1. Check if ElevenLabs API key is configured
    if not api_key:
        logger.warning("ElevenLabs speech-to-text invoked but ELEVENLABS_API_KEY is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs speech-to-text service is not configured. Missing ELEVENLABS_API_KEY.",
        )

    # 2. Validate MIME type and file format
    filename = file.filename or "recording.webm"
    content_type = file.content_type or "audio/webm"

    if not is_supported_audio_format(content_type, filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported audio format: '{content_type}'. "
                "Supported formats include WebM, OGG, WAV, MP3, MP4, M4A, AAC, and FLAC."
            ),
        )

    # 3. Read and validate audio file payload
    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded audio file: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read the uploaded audio file.",
        )

    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty. Please provide a valid recording.",
        )

    max_bytes = int(max_size_mb * 1024 * 1024)
    if len(content) > max_bytes:
        status_code_413 = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)
        raise HTTPException(
            status_code=status_code_413,
            detail=f"Audio file size ({len(content) / (1024 * 1024):.1f}MB) exceeds the maximum allowed limit of {max_size_mb:.0f}MB.",
        )

    # 4. Prepare multipart payload for ElevenLabs STT API
    # Clean normalized content type for upload header
    upload_mime = content_type.split(";")[0].strip().lower() if content_type else "audio/webm"
    if not upload_mime or upload_mime in ("application/octet-stream", "binary/octet-stream"):
        ext = Path(filename).suffix.lower()
        ext_to_mime = {
            ".webm": "audio/webm",
            ".ogg": "audio/ogg",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".mp4": "audio/mp4",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
        }
        upload_mime = ext_to_mime.get(ext, "audio/webm")

    files = {
        "file": (filename, content, upload_mime),
    }
    data: Dict[str, Any] = {
        "model_id": model_id,
    }

    if language_code and language_code.strip():
        data["language_code"] = language_code.strip()

    headers = {
        "xi-api-key": api_key,
    }

    # 5. Send request to ElevenLabs API
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                api_url,
                headers=headers,
                data=data,
                files=files,
            )

        if response.status_code == status.HTTP_200_OK:
            result = response.json()
            recognized_text = result.get("text", "").strip()
            detected_language = result.get("language_code")
            return {
                "text": recognized_text,
                "language_code": detected_language,
            }

        # Extract and sanitize upstream error details without exposing secrets
        raw_detail: Any = None
        error_type = ""
        error_code = ""
        try:
            error_json = response.json()
            if isinstance(error_json, dict):
                raw_detail = error_json.get("detail", error_json.get("message", error_json))
                if isinstance(raw_detail, dict):
                    error_type = str(raw_detail.get("type", ""))
                    error_code = str(raw_detail.get("code", ""))
        except Exception:
            raw_detail = response.text

        sanitized_detail = sanitize_upstream_error_detail(raw_detail, api_key)

        # Safe diagnostic logging: HTTP status and sanitized details only; never API keys or raw audio
        logger.warning(
            "ElevenLabs STT upstream HTTP %d: %s (type=%s, code=%s)",
            response.status_code,
            sanitized_detail,
            error_type,
            error_code,
        )

        # 1. Handle authentication failures (can be HTTP 401/403 OR HTTP 400 with authentication_error / invalid_api_key)
        is_auth_error = (
            response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
            or error_type == "authentication_error"
            or error_code in ("invalid_api_key", "unauthorized")
            or "api key" in sanitized_detail.lower()
        )
        if is_auth_error:
            logger.error("ElevenLabs STT upstream authentication failed (HTTP %d).", response.status_code)
            auth_msg = (
                f"Speech-to-text upstream authentication failed: {sanitized_detail}"
                if sanitized_detail
                else "Speech-to-text upstream authentication failed. Please verify API key configuration."
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=auth_msg,
            )

        # 2. Rate limit exceeded
        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            rate_msg = (
                f"Speech-to-text rate limit exceeded: {sanitized_detail}"
                if sanitized_detail
                else "Speech-to-text rate limit exceeded. Please try again shortly."
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=rate_msg,
            )

        # 3. Bad request or unprocessable entity (e.g., parameter or audio validation error)
        status_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
        if response.status_code in (status.HTTP_400_BAD_REQUEST, status_422, 422):
            param_msg = (
                f"Speech-to-text error: {sanitized_detail}"
                if sanitized_detail
                else "Audio could not be processed by the speech-to-text service. Please check the recording and try again."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=param_msg,
            )

        # 4. Upstream 5xx or unexpected error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Speech-to-text service returned an upstream error: {sanitized_detail or 'Service unavailable'}",
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.warning("ElevenLabs STT request timed out after %.1f seconds.", timeout_seconds)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Speech-to-text transcription timed out. Please try recording a shorter message.",
        )
    except httpx.RequestError as exc:
        logger.error("Failed to connect to ElevenLabs STT API: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to ElevenLabs speech-to-text service.",
        )
    except Exception as exc:
        logger.error("Unexpected error during speech transcription: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during speech-to-text processing.",
        )
