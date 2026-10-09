"""
Pydantic schemas for Speech-to-Text transcription.
"""

from typing import Optional
from pydantic import BaseModel, Field


class SpeechTranscriptionResponse(BaseModel):
    """
    Response schema for POST /api/speech/transcribe.
    Returns recognized text and detected or specified language code.
    """
    text: str = Field(..., description="Transcribed speech text")
    language_code: Optional[str] = Field(
        None,
        description="ISO language code of the recognized speech (e.g., 'en', 'hi', 'mr')",
    )
