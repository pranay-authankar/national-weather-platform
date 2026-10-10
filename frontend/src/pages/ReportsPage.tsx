import { useState, useEffect, useRef, useCallback, type FC, type FormEvent } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Send,
  Camera,
  Video,
  Upload,
  Trash2,
  RefreshCw,
  ImageIcon,
  Film,
  MapPin,
  X,
  Square,
  Circle,
  RotateCcw,
  Check,
} from 'lucide-react';
import { submitCitizenReport, uploadMediaEvidence } from '../services/reportsApi';
import { fetchStates, fetchDistricts } from '../services/locationsApi';
import type { CitizenReportPayload, LocationDistrict } from '../types/report';
import { EVENT_TYPES } from '../utils/constants';

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export const ReportsPage: FC = () => {
  // Form fields
  const [eventType, setEventType] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('');
  const [selectedCoords, setSelectedCoords] = useState<{ latitude: number; longitude: number } | null>(null);

  // States & Districts loading
  const [statesList, setStatesList] = useState<string[]>([]);
  const [statesLoading, setStatesLoading] = useState<boolean>(true);
  const [statesError, setStatesError] = useState<string | null>(null);

  const [districtsList, setDistrictsList] = useState<LocationDistrict[]>([]);
  const [districtsLoading, setDistrictsLoading] = useState<boolean>(false);
  const [districtsError, setDistrictsError] = useState<string | null>(null);

  // Media evidence
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);

  // Dedicated Camera Modal & Recording State
  const [activeCameraMode, setActiveCameraMode] = useState<'photo' | 'video' | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isInitializingCamera, setIsInitializingCamera] = useState<boolean>(false);

  // Video recording states
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordedVideoFile, setRecordedVideoFile] = useState<File | null>(null);
  const [recordedVideoPreviewUrl, setRecordedVideoPreviewUrl] = useState<string | null>(null);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);

  // Hidden file inputs refs for Upload File fallback
  const photoFileInputRef = useRef<HTMLInputElement | null>(null);
  const videoFileInputRef = useRef<HTMLInputElement | null>(null);

  // Camera & MediaRecorder refs
  const videoLiveRef = useRef<HTMLVideoElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingTimerRef = useRef<number | null>(null);

  // Form submission state
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitStatusText, setSubmitStatusText] = useState<string>('Submitting report...');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Fetch authoritative states on mount
  useEffect(() => {
    let isMounted = true;
    async function loadStates() {
      setStatesLoading(true);
      setStatesError(null);
      try {
        const fetched = await fetchStates();
        if (isMounted) {
          setStatesList(fetched);
        }
      } catch {
        if (isMounted) {
          setStatesError('Unable to load authoritative states list.');
        }
      } finally {
        if (isMounted) {
          setStatesLoading(false);
        }
      }
    }
    loadStates();
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch districts when state changes
  useEffect(() => {
    if (!selectedState) {
      return;
    }

    let isMounted = true;
    async function loadDistricts() {
      setDistrictsLoading(true);
      setDistrictsError(null);
      try {
        const fetched = await fetchDistricts(selectedState);
        if (isMounted) {
          setDistrictsList(fetched);
        }
      } catch {
        if (isMounted) {
          setDistrictsError('Unable to load districts for selected state.');
        }
      } finally {
        if (isMounted) {
          setDistrictsLoading(false);
        }
      }
    }

    loadDistricts();
    return () => {
      isMounted = false;
    };
  }, [selectedState]);

  // Clean up ObjectURLs on unmount or file change
  useEffect(() => {
    return () => {
      if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    };
  }, [photoPreviewUrl, videoPreviewUrl]);

  // Handle State selection
  const handleStateChange = (stateName: string) => {
    setSelectedState(stateName);
    setSelectedDistrict('');
    setSelectedCoords(null);
    if (!stateName) {
      setDistrictsList([]);
    }
    if (validationErrors.state) {
      setValidationErrors((prev) => ({ ...prev, state: '' }));
    }
    if (validationErrors.district) {
      setValidationErrors((prev) => ({ ...prev, district: '' }));
    }
  };

  // Handle District selection
  const handleDistrictChange = (districtName: string) => {
    setSelectedDistrict(districtName);
    const matched = districtsList.find((d) => d.district === districtName);
    if (matched) {
      setSelectedCoords({ latitude: matched.latitude, longitude: matched.longitude });
    } else {
      setSelectedCoords(null);
    }
    if (validationErrors.district) {
      setValidationErrors((prev) => ({ ...prev, district: '' }));
    }
  };

  // Handle Photo selection
  const handlePhotoSelect = (file: File | undefined) => {
    if (!file) return;

    // Validate image format
    if (!file.type.startsWith('image/')) {
      setSubmitError('Invalid file type: Please select an image file (JPG, PNG, WebP, etc.).');
      return;
    }

    // Validate size (10 MB)
    if (file.size > 10 * 1024 * 1024) {
      setSubmitError('Photo exceeds maximum file size limit of 10 MB.');
      return;
    }

    if (photoPreviewUrl) {
      URL.revokeObjectURL(photoPreviewUrl);
    }

    const preview = URL.createObjectURL(file);
    setPhotoFile(file);
    setPhotoPreviewUrl(preview);
    setSubmitError(null);
  };

  const handleRemovePhoto = () => {
    if (photoPreviewUrl) {
      URL.revokeObjectURL(photoPreviewUrl);
    }
    setPhotoFile(null);
    setPhotoPreviewUrl(null);
    if (photoFileInputRef.current) photoFileInputRef.current.value = '';
  };

  // Handle Video selection
  const handleVideoSelect = (file: File | undefined) => {
    if (!file) return;

    // Validate video format
    if (!file.type.startsWith('video/')) {
      setSubmitError('Invalid file type: Please select a valid video file (MP4, WebM, etc.).');
      return;
    }

    // Validate size (50 MB)
    if (file.size > 50 * 1024 * 1024) {
      setSubmitError('Video exceeds maximum file size limit of 50 MB.');
      return;
    }

    if (videoPreviewUrl) {
      URL.revokeObjectURL(videoPreviewUrl);
    }

    const preview = URL.createObjectURL(file);
    setVideoFile(file);
    setVideoPreviewUrl(preview);
    setSubmitError(null);
  };

  const handleRemoveVideo = () => {
    if (videoPreviewUrl) {
      URL.revokeObjectURL(videoPreviewUrl);
    }
    setVideoFile(null);
    setVideoPreviewUrl(null);
    if (videoFileInputRef.current) videoFileInputRef.current.value = '';
  };

  // -------------------------------------------------------------------------
  // Camera & Video Capture Lifecycle Handlers
  // -------------------------------------------------------------------------

  const openCamera = async (mode: 'photo' | 'video') => {
    setActiveCameraMode(mode);
    setCameraError(null);
    setIsRecording(false);
    setRecordedVideoFile(null);
    if (recordedVideoPreviewUrl) {
      URL.revokeObjectURL(recordedVideoPreviewUrl);
      setRecordedVideoPreviewUrl(null);
    }
    setRecordingDuration(0);
    setIsInitializingCamera(true);

    // Stop any existing stream before creating new one
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // ignore
        }
      });
      setCameraStream(null);
    }

    // 1. Browser compatibility & secure context check
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setCameraError(
        'Direct camera access is not supported in this browser. Camera capture requires a modern browser and a secure context (HTTPS or localhost). Please use the "Upload File" fallback instead.'
      );
      setIsInitializingCamera(false);
      return;
    }

    try {
      let stream: MediaStream;
      if (mode === 'photo') {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
      } else {
        // Video mode: try with audio enabled first
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: true,
          });
        } catch (audioErr) {
          console.warn('Microphone access unavailable or denied, falling back to video-only capture:', audioErr);
          // Fallback to video-only if microphone is denied or missing
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: false,
          });
        }
      }

      setCameraStream(stream);
    } catch (err: unknown) {
      let message = 'Unable to access device camera.';
      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          message =
            'Camera permission was denied. Please allow camera permissions in your browser or use the "Upload File" fallback.';
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          message =
            'No camera hardware detected on this device. Please connect a webcam or use the "Upload File" fallback.';
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          message =
            'Camera is currently in use by another application. Please close other camera programs and try again.';
        } else if (err.name === 'SecurityError') {
          message =
            'Camera access is blocked by browser security policy. Camera access requires a secure context (HTTPS or localhost).';
        } else {
          message = `Camera error (${err.name}): ${err.message || 'Unable to open camera.'}`;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setCameraError(message);
    } finally {
      setIsInitializingCamera(false);
    }
  };

  const closeCamera = useCallback(() => {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    if (cameraStream) {
      cameraStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // ignore
        }
      });
    }
    if (videoLiveRef.current) {
      videoLiveRef.current.srcObject = null;
    }
    if (recordedVideoPreviewUrl) {
      URL.revokeObjectURL(recordedVideoPreviewUrl);
    }
    setCameraStream(null);
    setActiveCameraMode(null);
    setCameraError(null);
    setIsRecording(false);
    setRecordedVideoFile(null);
    setRecordedVideoPreviewUrl(null);
    setRecordingDuration(0);
  }, [cameraStream, recordedVideoPreviewUrl]);

  // Bind live stream to camera video element
  useEffect(() => {
    if (videoLiveRef.current && cameraStream && !recordedVideoPreviewUrl) {
      videoLiveRef.current.srcObject = cameraStream;
      videoLiveRef.current.play().catch((e) => {
        console.warn('Live camera stream play warning:', e);
      });
    }
  }, [cameraStream, activeCameraMode, recordedVideoPreviewUrl]);

  // Keyboard shortcut: Escape key closes camera modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && activeCameraMode !== null) {
        closeCamera();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeCameraMode, closeCamera]);

  // Component unmount cleanup
  useEffect(() => {
    return () => {
      if (cameraStream) {
        cameraStream.getTracks().forEach((t) => t.stop());
      }
      if (recordingTimerRef.current) {
        window.clearInterval(recordingTimerRef.current);
      }
    };
  }, [cameraStream]);

  // Capture Photo frame from video via canvas
  const handleCapturePhoto = () => {
    const video = videoLiveRef.current;
    if (!video) {
      setCameraError('Camera live stream is not ready for capture.');
      return;
    }

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setCameraError('Unable to capture photo frame onto canvas.');
      return;
    }

    ctx.drawImage(video, 0, 0, width, height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError('Failed to capture photo from camera feed.');
          return;
        }
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const file = new File([blob], `observation_photo_${timestamp}.jpg`, { type: 'image/jpeg' });
        handlePhotoSelect(file);
        closeCamera();
      },
      'image/jpeg',
      0.92
    );
  };

  // Video recording controls
  const handleStartRecording = () => {
    if (!cameraStream) {
      setCameraError('Camera stream is not active.');
      return;
    }

    if (typeof MediaRecorder === 'undefined') {
      setCameraError(
        'MediaRecorder is not supported in this browser. Please use the "Upload File" fallback instead.'
      );
      return;
    }

    // Determine supported mime type
    const candidateMimes = [
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm;codecs=h264,opus',
      'video/webm',
      'video/mp4;codecs=avc1,mp4a',
      'video/mp4',
    ];
    let selectedMime = '';
    for (const m of candidateMimes) {
      if (MediaRecorder.isTypeSupported(m)) {
        selectedMime = m;
        break;
      }
    }

    try {
      const options = selectedMime ? { mimeType: selectedMime } : undefined;
      const recorder = new MediaRecorder(cameraStream, options);
      mediaRecorderRef.current = recorder;

      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const finalMime = recorder.mimeType || selectedMime || 'video/webm';
        const blob = new Blob(chunks, { type: finalMime });
        const ext = finalMime.includes('mp4') ? 'mp4' : 'webm';
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const file = new File([blob], `observation_video_${timestamp}.${ext}`, { type: finalMime });

        setRecordedVideoFile(file);
        const preview = URL.createObjectURL(blob);
        setRecordedVideoPreviewUrl(preview);
      };

      recorder.start(1000);
      setIsRecording(true);
      setRecordingDuration(0);

      recordingTimerRef.current = window.setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: unknown) {
      console.error('Failed to start MediaRecorder:', err);
      setCameraError(
        'Failed to start video recording. Your browser may not support the requested video format. Please use "Upload File" instead.'
      );
    }
  };

  const handleStopRecording = () => {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    setIsRecording(false);
  };

  const handleRetakeRecording = () => {
    if (recordedVideoPreviewUrl) {
      URL.revokeObjectURL(recordedVideoPreviewUrl);
    }
    setRecordedVideoFile(null);
    setRecordedVideoPreviewUrl(null);
    setRecordingDuration(0);
  };

  const handleUseRecordedVideo = () => {
    if (!recordedVideoFile) return;

    if (recordedVideoFile.size > 50 * 1024 * 1024) {
      setCameraError('Recorded video exceeds maximum size of 50 MB. Please record a shorter observation clip.');
      return;
    }

    handleVideoSelect(recordedVideoFile);
    closeCamera();
  };

  const handleFallbackToFileUpload = () => {
    const mode = activeCameraMode;
    closeCamera();
    if (mode === 'photo') {
      photoFileInputRef.current?.click();
    } else if (mode === 'video') {
      videoFileInputRef.current?.click();
    }
  };

  // Validate form
  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!eventType) {
      errors.eventType = 'Please select a weather event type.';
    }

    if (!description.trim()) {
      errors.description = 'Please provide a description of the weather event.';
    }

    if (!selectedState) {
      errors.state = 'Please select an administrative state.';
    }

    if (!selectedDistrict) {
      errors.district = 'Please select a city or district.';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Handle Form Submit
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);

    if (!validate()) {
      return;
    }

    setSubmitting(true);

    try {
      let uploadedImageUrl: string | null = null;
      let uploadedVideoUrl: string | null = null;

      // 1. Upload Photo if selected
      if (photoFile) {
        setSubmitStatusText('Uploading photo evidence...');
        try {
          const photoRes = await uploadMediaEvidence(photoFile);
          uploadedImageUrl = photoRes.url;
        } catch {
          setSubmitError('Failed to upload photo evidence to persistent storage. Please try again.');
          setSubmitting(false);
          return;
        }
      }

      // 2. Upload Video if selected
      if (videoFile) {
        setSubmitStatusText('Uploading video evidence...');
        try {
          const videoRes = await uploadMediaEvidence(videoFile);
          uploadedVideoUrl = videoRes.url;
        } catch {
          setSubmitError('Failed to upload video evidence to persistent storage. Please try again.');
          setSubmitting(false);
          return;
        }
      }

      // 3. Assemble report payload with automatic submission timestamp and resolved location
      setSubmitStatusText('Submitting citizen report...');
      const payload: CitizenReportPayload = {
        event_type: eventType,
        description: description.trim(),
        state: selectedState,
        district: selectedDistrict,
        city: selectedDistrict,
        latitude: selectedCoords?.latitude ?? null,
        longitude: selectedCoords?.longitude ?? null,
        timestamp: new Date().toISOString(), // Automatically recorded submission timestamp
        image_url: uploadedImageUrl,
        video_url: uploadedVideoUrl,
      };

      const response = await submitCitizenReport(payload);

      const refId = response?.event_id ? ` (Reference ID: ${response.event_id})` : '';
      setSubmitSuccess(`Citizen report submitted successfully.${refId}`);

      // Clear form
      setEventType('');
      setDescription('');
      setSelectedState('');
      setSelectedDistrict('');
      setSelectedCoords(null);
      handleRemovePhoto();
      handleRemoveVideo();
      setValidationErrors({});
    } catch {
      setSubmitError('Unable to submit citizen report. Please verify connection and retry.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="reports-page">
      <div className="page-header">
        <h2 className="page-title">Citizen Reports</h2>
        <p className="page-subtitle">
          Submit ground-level weather observations for real-time intelligence, analysis, and verification.
        </p>
      </div>

      <div className="report-form-container">
        {submitSuccess && (
          <div className="report-alert-banner success" role="status">
            <CheckCircle2 size={16} className="report-alert-icon" aria-hidden="true" />
            <span className="report-alert-text">{submitSuccess}</span>
          </div>
        )}

        {submitError && (
          <div className="report-alert-banner error" role="alert">
            <AlertCircle size={16} className="report-alert-icon" aria-hidden="true" />
            <span className="report-alert-text">{submitError}</span>
          </div>
        )}

        <form className="report-form" onSubmit={handleSubmit} noValidate>
          {/* Event Type */}
          <div className="form-group">
            <label htmlFor="report-event-type" className="form-label">
              Event Type <span className="required-star">*</span>
            </label>
            <select
              id="report-event-type"
              name="eventType"
              className={`form-control ${validationErrors.eventType ? 'error' : ''}`}
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value);
                if (validationErrors.eventType) {
                  setValidationErrors((prev) => ({ ...prev, eventType: '' }));
                }
              }}
              required
            >
              <option value="">Select a weather event type</option>
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            {validationErrors.eventType && (
              <span className="form-error-text">{validationErrors.eventType}</span>
            )}
          </div>

          {/* Description */}
          <div className="form-group">
            <label htmlFor="report-description" className="form-label">
              Description <span className="required-star">*</span>
            </label>
            <textarea
              id="report-description"
              name="description"
              rows={3}
              className={`form-control form-textarea ${validationErrors.description ? 'error' : ''}`}
              placeholder="Describe current weather conditions, severity, localized impact, or damage..."
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                if (validationErrors.description) {
                  setValidationErrors((prev) => ({ ...prev, description: '' }));
                }
              }}
              required
            />
            {validationErrors.description && (
              <span className="form-error-text">{validationErrors.description}</span>
            )}
          </div>

          {/* Authoritative Location Dropdowns (Replaces manual lat/lon) */}
          <div className="form-section-box">
            <div className="form-section-header">
              <span className="form-section-title">Observation Location</span>
              {selectedCoords && (
                <span className="location-coords-badge" title="Resolved authoritative coordinates">
                  <MapPin size={11} aria-hidden="true" />
                  {selectedCoords.latitude.toFixed(4)}°, {selectedCoords.longitude.toFixed(4)}°
                </span>
              )}
            </div>

            <div className="form-row-two-col">
              {/* State Dropdown */}
              <div className="form-group">
                <label htmlFor="report-state" className="form-label">
                  State / Union Territory <span className="required-star">*</span>
                </label>
                <select
                  id="report-state"
                  name="state"
                  className={`form-control ${validationErrors.state ? 'error' : ''}`}
                  value={selectedState}
                  onChange={(e) => handleStateChange(e.target.value)}
                  disabled={statesLoading || submitting}
                  required
                >
                  <option value="">
                    {statesLoading ? 'Loading authoritative states...' : 'Select State / Union Territory'}
                  </option>
                  {statesList.map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </select>
                {statesError && (
                  <span className="form-error-text">{statesError}</span>
                )}
                {validationErrors.state && (
                  <span className="form-error-text">{validationErrors.state}</span>
                )}
              </div>

              {/* City / District Dropdown */}
              <div className="form-group">
                <label htmlFor="report-district" className="form-label">
                  City / District <span className="required-star">*</span>
                </label>
                <select
                  id="report-district"
                  name="district"
                  className={`form-control ${validationErrors.district ? 'error' : ''}`}
                  value={selectedDistrict}
                  onChange={(e) => handleDistrictChange(e.target.value)}
                  disabled={!selectedState || districtsLoading || submitting}
                  required
                >
                  <option value="">
                    {!selectedState
                      ? 'Select state first'
                      : districtsLoading
                      ? 'Loading districts...'
                      : districtsError
                      ? 'Error loading districts'
                      : districtsList.length === 0
                      ? 'No districts available'
                      : 'Select City / District'}
                  </option>
                  {districtsList.map((d) => (
                    <option key={d.district} value={d.district}>
                      {d.district}
                    </option>
                  ))}
                </select>
                {districtsError && (
                  <div className="location-warning-text">
                    <span>{districtsError}</span>
                    <button
                      type="button"
                      className="btn-location-retry"
                      onClick={() => handleStateChange(selectedState)}
                    >
                      <RefreshCw size={11} aria-hidden="true" />
                      Retry
                    </button>
                  </div>
                )}
                {validationErrors.district && (
                  <span className="form-error-text">{validationErrors.district}</span>
                )}
              </div>
            </div>
          </div>

          {/* Media Evidence Capture & Upload */}
          <div className="form-section-box">
            <div className="form-section-header">
              <span className="form-section-title">Media Evidence</span>
              <span className="optional-tag">Photos & Videos (Optional)</span>
            </div>

            <div className="media-capture-grid">
              {/* Photo Evidence Card */}
              <div className="media-capture-card">
                <div className="media-card-header">
                  <div className="media-card-title-group">
                    <ImageIcon size={14} className="media-card-icon" aria-hidden="true" />
                    <span className="media-card-title">Photo Evidence</span>
                  </div>
                  {photoFile && (
                    <span className="media-file-size-badge">{formatFileSize(photoFile.size)}</span>
                  )}
                </div>

                {/* Hidden Input for File selection fallback */}
                <input
                  type="file"
                  accept="image/*"
                  ref={photoFileInputRef}
                  style={{ display: 'none' }}
                  onChange={(e) => handlePhotoSelect(e.target.files?.[0])}
                  disabled={submitting}
                />

                {photoPreviewUrl ? (
                  <div className="media-preview-container">
                    <img
                      src={photoPreviewUrl}
                      alt="Selected weather observation photo preview"
                      className="media-preview-image"
                    />
                    <div className="media-preview-actions">
                      <span className="media-preview-filename" title={photoFile?.name}>
                        {photoFile?.name}
                      </span>
                      <div className="media-btn-row">
                        <button
                          type="button"
                          className="btn-media-replace"
                          onClick={() => photoFileInputRef.current?.click()}
                          disabled={submitting}
                        >
                          Replace
                        </button>
                        <button
                          type="button"
                          className="btn-media-remove"
                          onClick={handleRemovePhoto}
                          disabled={submitting}
                          aria-label="Remove photo"
                        >
                          <Trash2 size={13} aria-hidden="true" />
                          <span>Remove</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="media-empty-state">
                    <p className="media-empty-text">Capture observation photo or choose from device</p>
                    <div className="media-action-buttons">
                      <button
                        type="button"
                        className="btn-media-action"
                        onClick={() => openCamera('photo')}
                        disabled={submitting}
                      >
                        <Camera size={14} aria-hidden="true" />
                        <span>Take Photo</span>
                      </button>
                      <button
                        type="button"
                        className="btn-media-action secondary"
                        onClick={() => photoFileInputRef.current?.click()}
                        disabled={submitting}
                      >
                        <Upload size={14} aria-hidden="true" />
                        <span>Upload File</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Video Evidence Card */}
              <div className="media-capture-card">
                <div className="media-card-header">
                  <div className="media-card-title-group">
                    <Film size={14} className="media-card-icon" aria-hidden="true" />
                    <span className="media-card-title">Video Evidence</span>
                  </div>
                  {videoFile && (
                    <span className="media-file-size-badge">{formatFileSize(videoFile.size)}</span>
                  )}
                </div>

                {/* Hidden Input for File selection fallback */}
                <input
                  type="file"
                  accept="video/*"
                  ref={videoFileInputRef}
                  style={{ display: 'none' }}
                  onChange={(e) => handleVideoSelect(e.target.files?.[0])}
                  disabled={submitting}
                />

                {videoPreviewUrl ? (
                  <div className="media-preview-container">
                    <video
                      src={videoPreviewUrl}
                      controls
                      className="media-preview-video"
                    />
                    <div className="media-preview-actions">
                      <span className="media-preview-filename" title={videoFile?.name}>
                        {videoFile?.name}
                      </span>
                      <div className="media-btn-row">
                        <button
                          type="button"
                          className="btn-media-replace"
                          onClick={() => videoFileInputRef.current?.click()}
                          disabled={submitting}
                        >
                          Replace
                        </button>
                        <button
                          type="button"
                          className="btn-media-remove"
                          onClick={handleRemoveVideo}
                          disabled={submitting}
                          aria-label="Remove video"
                        >
                          <Trash2 size={13} aria-hidden="true" />
                          <span>Remove</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="media-empty-state">
                    <p className="media-empty-text">Record weather video clip or choose from device</p>
                    <div className="media-action-buttons">
                      <button
                        type="button"
                        className="btn-media-action"
                        onClick={() => openCamera('video')}
                        disabled={submitting}
                      >
                        <Video size={14} aria-hidden="true" />
                        <span>Record Video</span>
                      </button>
                      <button
                        type="button"
                        className="btn-media-action secondary"
                        onClick={() => videoFileInputRef.current?.click()}
                        disabled={submitting}
                      >
                        <Upload size={14} aria-hidden="true" />
                        <span>Upload File</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Submit Action */}
          <div className="form-actions">
            <button
              type="submit"
              className="btn-submit-report"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <Loader2 size={16} className="btn-icon-spin" aria-hidden="true" />
                  <span>{submitStatusText}</span>
                </>
              ) : (
                <>
                  <Send size={15} aria-hidden="true" />
                  <span>Submit Report</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Dedicated Camera Interface Modal */}
      {activeCameraMode !== null && (
        <div
          className="camera-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="camera-modal-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeCamera();
          }}
        >
          <div className="camera-modal-card">
            {/* Modal Header */}
            <div className="camera-modal-header">
              <div className="camera-modal-title-group">
                {activeCameraMode === 'photo' ? (
                  <Camera size={18} className="camera-modal-icon" aria-hidden="true" />
                ) : (
                  <Video size={18} className="camera-modal-icon" aria-hidden="true" />
                )}
                <h3 id="camera-modal-title" className="camera-modal-title">
                  {activeCameraMode === 'photo' ? 'Take Observation Photo' : 'Record Observation Video'}
                </h3>
              </div>
              <button
                type="button"
                className="btn-camera-close"
                onClick={closeCamera}
                aria-label="Close camera interface"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="camera-modal-body">
              {cameraError ? (
                <div className="camera-error-container">
                  <div className="camera-error-icon-box">
                    <AlertCircle size={28} className="camera-error-icon" aria-hidden="true" />
                  </div>
                  <h4 className="camera-error-title">Camera Not Accessible</h4>
                  <p className="camera-error-text">{cameraError}</p>
                  <div className="camera-error-actions">
                    <button
                      type="button"
                      className="btn-modal-action primary"
                      onClick={handleFallbackToFileUpload}
                    >
                      <Upload size={14} aria-hidden="true" />
                      <span>Upload File Instead</span>
                    </button>
                    <button
                      type="button"
                      className="btn-modal-action secondary"
                      onClick={() => openCamera(activeCameraMode)}
                    >
                      <RefreshCw size={14} aria-hidden="true" />
                      <span>Retry Camera</span>
                    </button>
                  </div>
                </div>
              ) : isInitializingCamera ? (
                <div className="camera-loading-container">
                  <Loader2 size={32} className="btn-icon-spin camera-loading-spinner" aria-hidden="true" />
                  <p className="camera-loading-text">Connecting to camera hardware...</p>
                  <p className="camera-loading-subtext">
                    Please grant camera permission in your browser if prompted.
                  </p>
                </div>
              ) : (
                <div className="camera-viewport-container">
                  {/* Live Feed or Video Preview */}
                  {activeCameraMode === 'video' && recordedVideoPreviewUrl ? (
                    <div className="camera-video-preview-wrapper">
                      <video
                        src={recordedVideoPreviewUrl}
                        controls
                        autoPlay
                        playsInline
                        className="camera-video-element"
                      />
                      <div className="camera-recorded-meta">
                        <span>Duration: {formatDuration(recordingDuration)}</span>
                        {recordedVideoFile && (
                          <span>Size: {formatFileSize(recordedVideoFile.size)}</span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="camera-feed-wrapper">
                      <video
                        ref={videoLiveRef}
                        autoPlay
                        playsInline
                        muted
                        className="camera-video-element"
                      />

                      {/* Video Recording Status Badge */}
                      {activeCameraMode === 'video' && isRecording && (
                        <div className="camera-recording-indicator" role="status">
                          <span className="camera-rec-dot" aria-hidden="true" />
                          <span className="camera-rec-text">REC</span>
                          <span className="camera-rec-timer">{formatDuration(recordingDuration)}</span>
                        </div>
                      )}

                      {/* Photo framing overlay */}
                      {activeCameraMode === 'photo' && (
                        <div className="camera-framing-overlay" aria-hidden="true">
                          <div className="framing-corner top-left" />
                          <div className="framing-corner top-right" />
                          <div className="framing-corner bottom-left" />
                          <div className="framing-corner bottom-right" />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer Controls */}
            {!cameraError && !isInitializingCamera && (
              <div className="camera-modal-footer">
                {activeCameraMode === 'photo' ? (
                  <>
                    <button
                      type="button"
                      className="btn-modal-action secondary"
                      onClick={closeCamera}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn-modal-action primary capture-btn"
                      onClick={handleCapturePhoto}
                    >
                      <Camera size={16} aria-hidden="true" />
                      <span>Capture Photo</span>
                    </button>
                  </>
                ) : (
                  <>
                    {recordedVideoPreviewUrl ? (
                      <>
                        <button
                          type="button"
                          className="btn-modal-action secondary"
                          onClick={handleRetakeRecording}
                        >
                          <RotateCcw size={15} aria-hidden="true" />
                          <span>Record Again</span>
                        </button>
                        <button
                          type="button"
                          className="btn-modal-action primary"
                          onClick={handleUseRecordedVideo}
                        >
                          <Check size={16} aria-hidden="true" />
                          <span>Use This Video</span>
                        </button>
                        <button
                          type="button"
                          className="btn-modal-action text-btn"
                          onClick={closeCamera}
                        >
                          Cancel
                        </button>
                      </>
                    ) : isRecording ? (
                      <button
                        type="button"
                        className="btn-modal-action danger-stop"
                        onClick={handleStopRecording}
                      >
                        <Square size={16} aria-hidden="true" />
                        <span>Stop Recording ({formatDuration(recordingDuration)})</span>
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="btn-modal-action secondary"
                          onClick={closeCamera}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="btn-modal-action danger-record"
                          onClick={handleStartRecording}
                        >
                          <Circle size={15} className="rec-circle-icon" aria-hidden="true" />
                          <span>Start Recording</span>
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ReportsPage;
