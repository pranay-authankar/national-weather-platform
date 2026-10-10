/**
 * Type definitions for ElevenLabs Speech-to-Text feature.
 */

export interface SpeechTranscriptionResponse {
  text: string;
  language_code?: string | null;
}

export interface SpeechTranscriptionResult {
  text: string;
  languageCode?: string | null;
}
