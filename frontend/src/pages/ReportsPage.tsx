import { useState, type FC, type FormEvent } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  MapPin,
  Loader2,
  Send,
} from 'lucide-react';
import { submitCitizenReport } from '../services/reportsApi';
import type { CitizenReportPayload } from '../types/report';
import { EVENT_TYPES } from '../utils/constants';

function isValidUrl(urlString: string): boolean {
  try {
    const url = new URL(urlString);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

export const ReportsPage: FC = () => {
  const [eventType, setEventType] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [latitude, setLatitude] = useState<string>('');
  const [longitude, setLongitude] = useState<string>('');
  const [timestamp, setTimestamp] = useState<string>('');
  const [imageUrl, setImageUrl] = useState<string>('');
  const [videoUrl, setVideoUrl] = useState<string>('');

  const [locationLoading, setLocationLoading] = useState<boolean>(false);
  const [locationError, setLocationError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const handleGetLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation is not supported by your browser.');
      return;
    }

    setLocationLoading(true);
    setLocationError(null);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(6));
        setLongitude(position.coords.longitude.toFixed(6));
        setLocationLoading(false);
      },
      (err) => {
        setLocationLoading(false);
        if (err.code === err.PERMISSION_DENIED) {
          setLocationError('Location permission denied. Please enter manually.');
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setLocationError('Location unavailable. Please enter manually.');
        } else if (err.code === err.TIMEOUT) {
          setLocationError('Location request timed out. Please enter manually.');
        } else {
          setLocationError('Unable to retrieve location.');
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!eventType) {
      errors.eventType = 'Please select a weather event type.';
    }

    if (!description.trim()) {
      errors.description = 'Please provide a description of the weather event.';
    }

    const latNum = parseFloat(latitude);
    if (!latitude.trim() || isNaN(latNum)) {
      errors.latitude = 'Please enter a valid numeric latitude.';
    } else if (latNum < -90 || latNum > 90) {
      errors.latitude = 'Latitude must be between -90 and 90.';
    }

    const lonNum = parseFloat(longitude);
    if (!longitude.trim() || isNaN(lonNum)) {
      errors.longitude = 'Please enter a valid numeric longitude.';
    } else if (lonNum < -180 || lonNum > 180) {
      errors.longitude = 'Longitude must be between -180 and 180.';
    }

    if (!timestamp.trim()) {
      errors.timestamp = 'Please select the observation date and time.';
    } else {
      const parsedDate = new Date(timestamp);
      if (isNaN(parsedDate.getTime())) {
        errors.timestamp = 'Invalid observation date/time format.';
      }
    }

    if (imageUrl.trim() && !isValidUrl(imageUrl.trim())) {
      errors.imageUrl = 'Please enter a valid URL (starting with http:// or https://).';
    }

    if (videoUrl.trim() && !isValidUrl(videoUrl.trim())) {
      errors.videoUrl = 'Please enter a valid URL (starting with http:// or https://).';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);

    if (!validate()) {
      return;
    }

    setSubmitting(true);

    try {
      const payload: CitizenReportPayload = {
        event_type: eventType,
        description: description.trim(),
        latitude: parseFloat(latitude),
        longitude: parseFloat(longitude),
        timestamp: new Date(timestamp).toISOString(),
        image_url: imageUrl.trim() || null,
        video_url: videoUrl.trim() || null,
      };

      const response = await submitCitizenReport(payload);

      const refId = response?.event_id ? ` (Reference ID: ${response.event_id})` : '';
      setSubmitSuccess(`Report submitted successfully.${refId}`);

      // Clear form after successful submission
      setEventType('');
      setDescription('');
      setLatitude('');
      setLongitude('');
      setTimestamp('');
      setImageUrl('');
      setVideoUrl('');
      setValidationErrors({});
    } catch {
      setSubmitError('Unable to submit report.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="reports-page">
      <div className="page-header">
        <h2 className="page-title">Citizen Reports</h2>
        <p className="page-subtitle">Submit a weather observation for review.</p>
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
              <option value="">Select an event type</option>
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
              placeholder="Describe current weather conditions, severity, and local impact..."
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

          {/* Location Coordinates & Geolocation Helper */}
          <div className="form-section-box">
            <div className="form-section-header">
              <span className="form-section-title">Location Coordinates</span>
              <button
                type="button"
                className="btn-location-helper"
                onClick={handleGetLocation}
                disabled={locationLoading || submitting}
              >
                {locationLoading ? (
                  <Loader2 size={13} className="btn-icon-spin" aria-hidden="true" />
                ) : (
                  <MapPin size={13} aria-hidden="true" />
                )}
                <span>{locationLoading ? 'Detecting...' : 'Use my location'}</span>
              </button>
            </div>

            {locationError && (
              <div className="location-warning-text" role="status">
                <AlertCircle size={13} aria-hidden="true" />
                <span>{locationError}</span>
              </div>
            )}

            <div className="form-row-two-col">
              <div className="form-group">
                <label htmlFor="report-latitude" className="form-label">
                  Latitude <span className="required-star">*</span>
                </label>
                <input
                  type="number"
                  id="report-latitude"
                  name="latitude"
                  step="any"
                  placeholder="e.g. 19.0760"
                  className={`form-control ${validationErrors.latitude ? 'error' : ''}`}
                  value={latitude}
                  onChange={(e) => {
                    setLatitude(e.target.value);
                    if (validationErrors.latitude) {
                      setValidationErrors((prev) => ({ ...prev, latitude: '' }));
                    }
                  }}
                  required
                />
                {validationErrors.latitude && (
                  <span className="form-error-text">{validationErrors.latitude}</span>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="report-longitude" className="form-label">
                  Longitude <span className="required-star">*</span>
                </label>
                <input
                  type="number"
                  id="report-longitude"
                  name="longitude"
                  step="any"
                  placeholder="e.g. 72.8777"
                  className={`form-control ${validationErrors.longitude ? 'error' : ''}`}
                  value={longitude}
                  onChange={(e) => {
                    setLongitude(e.target.value);
                    if (validationErrors.longitude) {
                      setValidationErrors((prev) => ({ ...prev, longitude: '' }));
                    }
                  }}
                  required
                />
                {validationErrors.longitude && (
                  <span className="form-error-text">{validationErrors.longitude}</span>
                )}
              </div>
            </div>
          </div>

          {/* Observation Time */}
          <div className="form-group">
            <label htmlFor="report-timestamp" className="form-label">
              Observation Time <span className="required-star">*</span>
            </label>
            <input
              type="datetime-local"
              id="report-timestamp"
              name="timestamp"
              className={`form-control ${validationErrors.timestamp ? 'error' : ''}`}
              value={timestamp}
              onChange={(e) => {
                setTimestamp(e.target.value);
                if (validationErrors.timestamp) {
                  setValidationErrors((prev) => ({ ...prev, timestamp: '' }));
                }
              }}
              required
            />
            {validationErrors.timestamp && (
              <span className="form-error-text">{validationErrors.timestamp}</span>
            )}
          </div>

          {/* Media Evidence URLs */}
          <div className="form-row-two-col">
            <div className="form-group">
              <label htmlFor="report-image-url" className="form-label">
                Image URL <span className="optional-tag">(optional)</span>
              </label>
              <input
                type="url"
                id="report-image-url"
                name="imageUrl"
                placeholder="https://example.com/photo.jpg"
                className={`form-control ${validationErrors.imageUrl ? 'error' : ''}`}
                value={imageUrl}
                onChange={(e) => {
                  setImageUrl(e.target.value);
                  if (validationErrors.imageUrl) {
                    setValidationErrors((prev) => ({ ...prev, imageUrl: '' }));
                  }
                }}
              />
              {validationErrors.imageUrl && (
                <span className="form-error-text">{validationErrors.imageUrl}</span>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="report-video-url" className="form-label">
                Video URL <span className="optional-tag">(optional)</span>
              </label>
              <input
                type="url"
                id="report-video-url"
                name="videoUrl"
                placeholder="https://example.com/video.mp4"
                className={`form-control ${validationErrors.videoUrl ? 'error' : ''}`}
                value={videoUrl}
                onChange={(e) => {
                  setVideoUrl(e.target.value);
                  if (validationErrors.videoUrl) {
                    setValidationErrors((prev) => ({ ...prev, videoUrl: '' }));
                  }
                }}
              />
              {validationErrors.videoUrl && (
                <span className="form-error-text">{validationErrors.videoUrl}</span>
              )}
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
                  <span>Submitting report...</span>
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
    </div>
  );
};

export default ReportsPage;
