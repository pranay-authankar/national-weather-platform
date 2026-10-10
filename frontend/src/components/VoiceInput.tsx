import { useState, useRef, useEffect, type FC } from 'react';
import {
  Mic,
  Square,
  Loader2,
  X,
  AlertCircle,
  CheckCircle2,
  Globe,
} from 'lucide-react';
import { transcribeAudio, extractSpeechErrorMessage } from '../services/speechApi';

interface VoiceInputProps {
  onTranscript: (text: string, languageCode?: string | null) => void;
  disabled?: boolean;
}

const SUPPORTED_LANGUAGES = [
  { code: 'auto', label: 'Auto-detect' },
  { code: 'hi', label: 'Hindi (हिंदी)' },
  { code: 'en', label: 'English' },
  { code: 'mr', label: 'Marathi (मराठी)' },
  { code: 'bn', label: 'Bengali (বাংলা)' },
  { code: 'ta', label: 'Tamil (தமிழ்)' },
  { code: 'te', label: 'Telugu (తెలుగు)' },
  { code: 'gu', label: 'Gujarati (ગુજરાતી)' },
  { code: 'kn', label: 'Kannada (ಕನ್ನಡ)' },
  { code: 'ml', label: 'Malayalam (മലയാളം)' },
  { code: 'pa', label: 'Punjabi (ਪੰਜਾਬੀ)' },
  { code: 'or', label: 'Odia (ଓଡ଼ିଆ)' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
];

const MAX_RECORDING_SECONDS = 120; // 2 minutes maximum recording length

const checkBrowserSupport = (): boolean => {
  return (
    typeof window !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof window.MediaRecorder !== 'undefined'
  );
};

const CANDIDATE_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
  'audio/ogg',
  'audio/aac',
  'audio/wav',
];

function pickSupportedMimeType(): string {
  if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return '';
  }
  for (const candidate of CANDIDATE_MIME_TYPES) {
    try {
      if (MediaRecorder.isTypeSupported(candidate)) {
        return candidate;
      }
    } catch {
      // Continue checking next candidate
    }
  }
  return '';
}

export const VoiceInput: FC<VoiceInputProps> = ({ onTranscript, disabled = false }) => {
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successInfo, setSuccessInfo] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<string>('auto');
  const [isSupported] = useState<boolean>(checkBrowserSupport);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  const formatTimer = (totalSeconds: number): string => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };

  const startRecording = async () => {
    setErrorMessage(null);
    setSuccessInfo(null);
    audioChunksRef.current = [];

    if (!isSupported) {
      setErrorMessage('Voice input is not supported in this browser. Please use Chrome, Edge, or Firefox.');
      return;
    }

    try {
      // Microphone permission requested only when user explicitly clicks record
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Determine supported MIME type across various browsers (Chrome, Firefox, Safari, Edge)
      const preferredMime = pickSupportedMimeType();
      const recorder = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stopStream();
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        const chunks = audioChunksRef.current;
        if (chunks.length === 0) {
          setIsRecording(false);
          return;
        }

        // Preserve actual MediaRecorder MIME type reported by the browser instance
        const actualMimeType = recorder.mimeType || preferredMime || 'audio/webm';
        const audioBlob = new Blob(chunks, { type: actualMimeType });
        if (audioBlob.size === 0) {
          setIsRecording(false);
          setErrorMessage('No audio captured. Please try speaking into your microphone.');
          return;
        }

        await processTranscription(audioBlob);
      };

      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
      setRecordingSeconds(0);

      // Start timer
      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev + 1 >= MAX_RECORDING_SECONDS) {
            // Automatically stop and transcribe when max duration is reached
            stopRecording();
            return MAX_RECORDING_SECONDS;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err: unknown) {
      stopStream();
      setIsRecording(false);

      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setErrorMessage('Microphone access was denied. Please allow microphone permissions in your browser.');
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          setErrorMessage('No microphone found on this device. Please connect a microphone.');
        } else {
          setErrorMessage(`Microphone error: ${err.message}`);
        }
      } else {
        setErrorMessage('Unable to access microphone. Please check your browser audio settings.');
      }
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const cancelRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      // Detach onstop handler so we don't submit audio
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
    }
    stopStream();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    audioChunksRef.current = [];
    setIsRecording(false);
    setRecordingSeconds(0);
    setErrorMessage(null);
  };

  const processTranscription = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    setErrorMessage(null);

    try {
      const result = await transcribeAudio(
        audioBlob,
        selectedLanguage === 'auto' ? undefined : selectedLanguage
      );

      if (result.text && result.text.trim()) {
        onTranscript(result.text.trim(), result.languageCode);
        const langLabel = result.languageCode
          ? SUPPORTED_LANGUAGES.find((l) => l.code === result.languageCode)?.label || result.languageCode
          : 'Detected';
        setSuccessInfo(`Transcribed (${langLabel})`);
        setTimeout(() => setSuccessInfo(null), 5000);
      } else {
        setErrorMessage('No speech could be recognized. Please try speaking clearly and closer to the microphone.');
      }
    } catch (err: unknown) {
      const errorMsg = extractSpeechErrorMessage(err);
      setErrorMessage(errorMsg);
    } finally {
      setIsTranscribing(false);
      setRecordingSeconds(0);
    }
  };

  return (
    <div className="voice-input-wrapper" aria-label="ElevenLabs Speech-to-Text Input">
      <div className="voice-input-controls">
        {/* State 1: Idle (Show Start Mic Button) */}
        {!isRecording && !isTranscribing && (
          <div className="voice-input-idle-row">
            <button
              type="button"
              id="btn-voice-input-record"
              className="btn-voice-record"
              onClick={startRecording}
              disabled={disabled || !isSupported}
              title={
                !isSupported
                  ? 'Voice input not supported in this browser'
                  : 'Click to speak your description (ElevenLabs STT)'
              }
              aria-label="Start voice recording"
            >
              <Mic size={14} className="voice-mic-icon" aria-hidden="true" />
              <span>Voice Input</span>
            </button>

            {/* Optional Language Bias Selector */}
            <div className="voice-lang-selector-wrap">
              <Globe size={12} className="voice-lang-icon" aria-hidden="true" />
              <select
                id="voice-language-select"
                className="voice-lang-select"
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value)}
                disabled={disabled}
                aria-label="Select spoken language for transcription"
              >
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* State 2: Actively Recording */}
        {isRecording && (
          <div className="voice-recording-active" role="status" aria-live="polite">
            <div className="voice-pulse-indicator" aria-hidden="true">
              <span className="pulse-dot"></span>
              <span className="recording-text">Listening...</span>
            </div>

            <span className="recording-timer" aria-label={`Recording time: ${formatTimer(recordingSeconds)}`}>
              {formatTimer(recordingSeconds)} / {formatTimer(MAX_RECORDING_SECONDS)}
            </span>

            <div className="voice-recording-actions">
              <button
                type="button"
                id="btn-voice-input-stop"
                className="btn-voice-action stop"
                onClick={stopRecording}
                title="Finish recording and transcribe"
                aria-label="Stop recording and transcribe"
              >
                <Square size={13} fill="currentColor" aria-hidden="true" />
                <span>Stop & Transcribe</span>
              </button>

              <button
                type="button"
                id="btn-voice-input-cancel"
                className="btn-voice-action cancel"
                onClick={cancelRecording}
                title="Cancel recording"
                aria-label="Cancel recording"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}

        {/* State 3: Transcribing Audio */}
        {isTranscribing && (
          <div className="voice-transcribing-status" role="status" aria-live="polite">
            <Loader2 size={14} className="voice-spinner" aria-hidden="true" />
            <span className="transcribing-text">ElevenLabs transcribing speech...</span>
          </div>
        )}

        {/* Brief Success Info Pill */}
        {successInfo && !isRecording && !isTranscribing && (
          <div className="voice-status-pill success" role="status">
            <CheckCircle2 size={13} className="pill-icon" aria-hidden="true" />
            <span>{successInfo}</span>
          </div>
        )}
      </div>

      {/* Error Alert Display */}
      {errorMessage && (
        <div className="voice-error-banner" role="alert">
          <AlertCircle size={14} className="error-icon" aria-hidden="true" />
          <span className="error-text">{errorMessage}</span>
          <button
            type="button"
            className="btn-dismiss-error"
            onClick={() => setErrorMessage(null)}
            aria-label="Dismiss voice error"
          >
            <X size={12} aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  );
};

export default VoiceInput;
