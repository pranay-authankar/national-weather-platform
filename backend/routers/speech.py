"""
API Router for Speech-to-Text operations powered by ElevenLabs.
Implements POST /api/speech/transcribe.
"""

from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile, status

from schemas.speech import SpeechTranscriptionResponse
from services.speech_service import transcribe_audio_file

router = APIRouter(prefix="/api/speech", tags=["Speech to Text"])


@router.post(
    "/transcribe",
    response_model=SpeechTranscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe audio to text using ElevenLabs",
    description=(
        "Transcribes an uploaded audio file using ElevenLabs' official Speech-to-Text API "
        "(model: scribe_v2). Supports multilingual audio with automatic language detection, "
        "or optional language biasing via language_code. Does not store audio or create database records."
    ),
)
async def transcribe_speech(
    file: UploadFile = File(..., description="Audio file recording to transcribe (e.g., WebM, OGG, WAV, MP3)"),
    language_code: Optional[str] = Form(
        None,
        description="Optional ISO language code (e.g., 'en', 'hi', 'mr'). When omitted, language is detected automatically.",
    ),
) -> SpeechTranscriptionResponse:
    """
    Handle POST /api/speech/transcribe:
    - Validates audio file presence, MIME type, and size limits.
    - Submits audio to ElevenLabs Speech-to-Text API (scribe_v2).
    - Returns transcribed text and detected language code.
    """
    result = await transcribe_audio_file(file=file, language_code=language_code)
    return SpeechTranscriptionResponse(
        text=result["text"],
        language_code=result.get("language_code"),
    )
