/**
 * Speech API service for communicating with the backend ElevenLabs transcription endpoint.
 * Handles audio upload, language options, and safe error message extraction.
 */

import axios from 'axios';
import apiClient from './api.ts';
import type { SpeechTranscriptionResponse, SpeechTranscriptionResult } from '../types/speech';

/**
 * Extract user-friendly error message from an unknown error or AxiosError.
 */
export function extractSpeechErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return 'Unable to reach the server. Please check your network connection.';
    }
    const status = error.response.status;
    const detail = error.response.data?.detail;

    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }

    if (status === 503) {
      return 'Voice transcription service is not configured on the server (missing API key).';
    }
    if (status === 502) {
      return 'Speech-to-text service is temporarily unavailable or upstream error occurred.';
    }
    if (status === 429) {
      return 'Voice transcription rate limit reached. Please wait a moment before trying again.';
    }
    if (status === 504) {
      return 'Transcription timed out. Please try recording a shorter message.';
    }
    if (status === 413) {
      return 'Audio recording is too large. Please record a shorter message.';
    }
    if (status === 400) {
      return 'Audio format could not be processed. Please try again.';
    }
    return `Server error (${status}): Failed to transcribe audio.`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'An unexpected error occurred during audio transcription.';
}

/**
 * Transcribe an audio Blob via POST /api/speech/transcribe.
 * 
 * @param audioBlob Audio recording Blob from MediaRecorder
 * @param languageCode Optional language code (e.g., 'hi', 'en') or 'auto'
 */
export async function transcribeAudio(
  audioBlob: Blob,
  languageCode?: string
): Promise<SpeechTranscriptionResult> {
  const formData = new FormData();

  // Determine appropriate filename based on container MIME type
  let filename = 'recording.webm';
  if (audioBlob.type.includes('mp4')) {
    filename = 'recording.mp4';
  } else if (audioBlob.type.includes('ogg')) {
    filename = 'recording.ogg';
  } else if (audioBlob.type.includes('wav')) {
    filename = 'recording.wav';
  }

  formData.append('file', audioBlob, filename);

  if (languageCode && languageCode.trim() && languageCode !== 'auto') {
    formData.append('language_code', languageCode.trim());
  }

  const response = await apiClient.post<SpeechTranscriptionResponse>(
    '/api/speech/transcribe',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 45000,
    }
  );

  return {
    text: response.data.text,
    languageCode: response.data.language_code,
  };
}
