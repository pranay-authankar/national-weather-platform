"""
Service module for ElevenLabs Speech-to-Text integration.
Transcribes audio recordings using ElevenLabs' official Speech-to-Text API (model: scribe_v2).
Never leaks API keys or secrets in logs or responses.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set
from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile, status
import httpx

logger = logging.getLogger(__name__)

# Ensure backend/.env is loaded without overriding environment variables
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

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


def get_elevenlabs_config() -> Dict[str, Any]:
    """
    Retrieve ElevenLabs configuration from environment variables.
    Re-checks environment in case variables were updated dynamically.
    """
    load_dotenv(dotenv_path=env_path, override=False)
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
    upload_mime = content_type.split(";")[0].strip() or "audio/webm"
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

        # Handle specific ElevenLabs error status codes
        if response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            logger.error("ElevenLabs STT upstream authentication failed (HTTP %d).", response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Speech-to-text upstream authentication failed. Please verify API key configuration.",
            )

        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            logger.warning("ElevenLabs STT rate limit exceeded.")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Speech-to-text rate limit exceeded. Please try again shortly.",
            )

        if response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY):
            logger.warning("ElevenLabs STT rejected audio input (HTTP %d).", response.status_code)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Audio could not be processed by the speech-to-text service. Please check the recording and try again.",
            )

        logger.error("ElevenLabs STT returned unexpected HTTP %d.", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Speech-to-text service returned an unexpected upstream error.",
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
