import { useState, useEffect, useCallback, type FC, type FormEvent } from 'react';
import {
  AlertCircle,
  Activity,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Layers,
  Info,
  X,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { getEvents, getEventById } from '../services/eventsApi';
import { getAnalyticsSummary } from '../services/analyticsApi';
import type { WeatherEvent, EventFilters, EventsResponse } from '../types/event';
import type { AnalyticsSummary } from '../types/analytics';
import { VERIFICATION_STATUSES, EVENT_TYPES, DATA_SOURCES } from '../utils/constants';

const PAGE_SIZE = 10;

function formatLocation(event: WeatherEvent): string {
  const parts = [event.city, event.district, event.state].filter(Boolean);
  return parts.length > 0 ? parts.join(', ') : 'Location unavailable';
}

function formatTimestamp(isoString: string): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  } catch {
    return isoString;
  }
}

function hasMeasurements(event: WeatherEvent): boolean {
  return (
    event.rainfall !== null ||
    event.temperature !== null ||
    event.humidity !== null ||
    event.wind_speed !== null ||
    event.pressure !== null
  );
}

function getStatusCount(
  summary: AnalyticsSummary | null,
  statusName: string,
  directCount?: number
): number {
  if (!summary) return 0;
  const list = summary.events_by_verification || summary.verification_breakdown;
  if (list && Array.isArray(list)) {
    const found = list.find((item) => item.status.toLowerCase() === statusName.toLowerCase());
    if (found && typeof found.count === 'number') {
      return found.count;
    }
  }
  return typeof directCount === 'number' ? directCount : 0;
}

export const VerificationPage: FC = () => {
  const [events, setEvents] = useState<WeatherEvent[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [appliedFilters, setAppliedFilters] = useState<EventFilters>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);

  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedEventType, setSelectedEventType] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<string>('');

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<WeatherEvent | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const processFetchedEvents = (data?: EventsResponse) => {
    const fetchedEvents = data?.data ?? [];
    const pagination = data?.pagination;

    setEvents(fetchedEvents);
    setTotal(pagination?.total ?? fetchedEvents.length);
    setCurrentPage(pagination?.page ?? 1);
    setTotalPages(pagination?.total_pages ?? (fetchedEvents.length > 0 ? 1 : 0));
    setLoading(false);
  };

  const fetchEvents = useCallback((page: number = 1, filters?: EventFilters) => {
    setLoading(true);
    setError(null);

    getEvents({ page, page_size: PAGE_SIZE, ...filters })
      .then((data) => {
        processFetchedEvents(data);
      })
      .catch(() => {
        setError('Unable to load verification data.');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let isMounted = true;

    // Load initial events
    getEvents({ page: 1, page_size: PAGE_SIZE })
      .then((data) => {
        if (!isMounted) return;
        processFetchedEvents(data);
      })
      .catch(() => {
        if (!isMounted) return;
        setError('Unable to load verification data.');
        setLoading(false);
      });

    // Load analytics summary for verification metrics
    getAnalyticsSummary()
      .then((data) => {
        if (!isMounted) return;
        setSummary(data);
      })
      .catch(() => {
        // Non-critical: summary cards will fallback gracefully
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleApplyFilters = (e: FormEvent) => {
    e.preventDefault();

    const filters: EventFilters = {};
    if (selectedStatus) filters.verification_status = selectedStatus;
    if (selectedEventType) filters.event_type = selectedEventType;
    if (selectedSource) filters.source = selectedSource;

    setAppliedFilters(filters);
    fetchEvents(1, filters);
  };

  const handleClearFilters = () => {
    setSelectedStatus('');
    setSelectedEventType('');
    setSelectedSource('');

    setAppliedFilters({});
    fetchEvents(1, {});
  };

  const handlePreviousPage = () => {
    if (currentPage <= 1 || loading) return;
    const targetPage = currentPage - 1;
    fetchEvents(targetPage, appliedFilters);
  };

  const handleNextPage = () => {
    const maxPages = totalPages > 0 ? totalPages : 1;
    if (currentPage >= maxPages || loading) return;
    const targetPage = currentPage + 1;
    fetchEvents(targetPage, appliedFilters);
  };

  const handleSelectEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    setSelectedEvent(null);
    setDetailLoading(true);
    setDetailError(null);

    getEventById(eventId)
      .then((data) => {
        setSelectedEvent(data);
        setDetailLoading(false);
      })
      .catch(() => {
        setDetailError('Unable to load event details.');
        setDetailLoading(false);
      });
  };

  const handleCloseDetail = useCallback(() => {
    setSelectedEventId(null);
    setSelectedEvent(null);
    setDetailLoading(false);
    setDetailError(null);
  }, []);

  useEffect(() => {
    if (!selectedEventId) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleCloseDetail();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selectedEventId, handleCloseDetail]);

  const isFiltered = Boolean(
    appliedFilters.verification_status ||
    appliedFilters.event_type ||
    appliedFilters.source
  );

  const totalEventsMetric = summary?.total_events ?? (events.length > 0 ? total : 0);
  const verifiedCount = getStatusCount(summary, 'Verified', summary?.verified_events);
  const likelyCount = getStatusCount(summary, 'Likely', summary?.likely_events);
  const unverifiedCount = getStatusCount(summary, 'Unverified', summary?.unverified_events);
  const rejectedCount = getStatusCount(summary, 'Rejected', summary?.rejected_events);
  const duplicateCount = getStatusCount(summary, 'Duplicate', summary?.duplicate_events);

  return (
    <div className="verification-page">
      <div className="page-header">
        <h2 className="page-title">Event Verification & Audit</h2>
        <p className="page-subtitle">
          Inspect event verification status, confidence, and duplicate information.
        </p>
      </div>

      <div className="verification-notice-banner" role="note">
        <Info size={15} className="verification-notice-icon" aria-hidden="true" />
        <span className="verification-notice-text">
          Read-only inspection interface. Verification statuses and confidence scoring are assigned
          by the automated backend verification pipeline.
        </span>
      </div>

      {/* Summary Metrics Cards */}
      <div className="verification-summary-cards" aria-label="Verification Summary Metrics">
        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Total Events</span>
            <Activity size={16} className="summary-card-icon total" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{totalEventsMetric}</div>
          <div className="summary-card-sub">Recorded weather events</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Verified</span>
            <ShieldCheck size={16} className="summary-card-icon verified" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{verifiedCount}</div>
          <div className="summary-card-sub">Confirmed accuracy</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Likely</span>
            <CheckCircle2 size={16} className="summary-card-icon likely" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{likelyCount}</div>
          <div className="summary-card-sub">High probability match</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Unverified</span>
            <AlertTriangle size={16} className="summary-card-icon unverified" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{unverifiedCount}</div>
          <div className="summary-card-sub">Pending pipeline analysis</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Rejected</span>
            <XCircle size={16} className="summary-card-icon rejected" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{rejectedCount}</div>
          <div className="summary-card-sub">Refuted or invalid data</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Duplicate</span>
            <Layers size={16} className="summary-card-icon duplicate" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{duplicateCount}</div>
          <div className="summary-card-sub">Cross-referenced duplicates</div>
        </div>
      </div>

      {/* Verification Events Section */}
      <div className="dashboard-events-section verification-events-section">
        <div className="dashboard-section-header">
          <h3 className="section-title">Verification Event Queue</h3>
          {!loading && !error && (
            <span className="section-count">
              {total} {total === 1 ? 'event' : 'events'}
            </span>
          )}
        </div>

        {/* Filter Controls Bar */}
        <form className="dashboard-filter-bar verification-filter-bar" onSubmit={handleApplyFilters}>
          <div className="filter-row filter-row-primary">
            <span className="filter-label">Filters</span>

            <select
              className="filter-control filter-select"
              aria-label="Filter by verification status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="">All Statuses</option>
              {VERIFICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>

            <select
              className="filter-control filter-select"
              aria-label="Filter by event type"
              value={selectedEventType}
              onChange={(e) => setSelectedEventType(e.target.value)}
            >
              <option value="">All Event Types</option>
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>

            <select
              className="filter-control filter-select"
              aria-label="Filter by data source"
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
            >
              <option value="">All Sources</option>
              {DATA_SOURCES.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>

            <div className="filter-actions">
              <button type="submit" className="filter-btn filter-btn-apply">
                Apply Filters
              </button>
              <button
                type="button"
                className="filter-btn filter-btn-clear"
                onClick={handleClearFilters}
              >
                Clear
              </button>
            </div>
          </div>
        </form>

        {loading && (
          <div className="dashboard-state-box loading">
            <span className="dashboard-state-text">Loading verification data...</span>
          </div>
        )}

        {!loading && error && (
          <div className="dashboard-error-banner" role="alert">
            <AlertCircle size={15} className="error-banner-icon" aria-hidden="true" />
            <span className="error-banner-text">{error}</span>
          </div>
        )}

        {!loading && !error && events.length === 0 && (
          <div className="dashboard-state-box empty">
            <span className="dashboard-state-text">
              {isFiltered
                ? 'No events match the selected verification filters.'
                : 'No events available for verification review.'}
            </span>
          </div>
        )}

        {!loading && !error && events.length > 0 && (
          <>
            <div className="events-table-container">
              <table className="events-table verification-table">
                <thead>
                  <tr>
                    <th scope="col">Event Type</th>
                    <th scope="col">Source</th>
                    <th scope="col">Location</th>
                    <th scope="col">Timestamp</th>
                    <th scope="col">Verification Status</th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Duplicate</th>
                    <th scope="col" className="col-actions text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr
                      key={event.event_id}
                      className={`event-row clickable ${selectedEventId === event.event_id ? 'selected' : ''}`}
                      onClick={() => handleSelectEvent(event.event_id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleSelectEvent(event.event_id);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      aria-label={`Inspect event ${event.event_id}: ${event.event_type} in ${formatLocation(event)}`}
                    >
                      <td>
                        <span className="event-type-badge">{event.event_type}</span>
                      </td>
                      <td className="event-cell-source">{event.source}</td>
                      <td className="event-cell-location">{formatLocation(event)}</td>
                      <td className="event-cell-time">{formatTimestamp(event.event_timestamp)}</td>
                      <td>
                        <span
                          className={`verification-badge ${(event.verification_status || '').toLowerCase()}`}
                        >
                          {event.verification_status || 'Unverified'}
                        </span>
                      </td>
                      <td className="event-cell-confidence">
                        {event.confidence_score !== null && event.confidence_score !== undefined ? (
                          <span className="confidence-pill">{event.confidence_score}%</span>
                        ) : (
                          <span className="table-cell-muted">—</span>
                        )}
                      </td>
                      <td>
                        {event.duplicate_of ? (
                          <span
                            className="verification-badge duplicate"
                            title={`Duplicate of ${event.duplicate_of}`}
                          >
                            Duplicate
                          </span>
                        ) : (
                          <span className="table-cell-muted">—</span>
                        )}
                      </td>
                      <td className="col-actions text-right">
                        <button
                          type="button"
                          className="table-action-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectEvent(event.event_id);
                          }}
                          aria-label={`Inspect details for event ${event.event_id}`}
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="dashboard-pagination" aria-label="Table pagination">
              <button
                type="button"
                className="pagination-btn"
                onClick={handlePreviousPage}
                disabled={currentPage <= 1 || loading}
                aria-label="Previous page"
              >
                <ChevronLeft size={15} aria-hidden="true" />
                <span>Previous</span>
              </button>

              <span className="pagination-info" aria-live="polite">
                Page {currentPage} of {totalPages > 0 ? totalPages : 1}
              </span>

              <button
                type="button"
                className="pagination-btn"
                onClick={handleNextPage}
                disabled={currentPage >= (totalPages > 0 ? totalPages : 1) || loading}
                aria-label="Next page"
              >
                <span>Next</span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Read-Only Event Details Drawer */}
      {selectedEventId && (
        <>
          <div
            className="drawer-backdrop"
            onClick={handleCloseDetail}
            aria-hidden="true"
          />
          <aside
            className="event-detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="detail-drawer-title"
          >
            <div className="drawer-header">
              <h3 id="detail-drawer-title" className="drawer-title">
                Event Verification Details
              </h3>
              <button
                type="button"
                className="drawer-close-btn"
                onClick={handleCloseDetail}
                aria-label="Close event details"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="drawer-body">
              {detailLoading && (
                <div className="detail-state-box loading">
                  <span className="detail-state-text">Loading event details...</span>
                </div>
              )}

              {!detailLoading && detailError && (
                <div className="detail-error-banner" role="alert">
                  <AlertCircle size={15} className="error-banner-icon" aria-hidden="true" />
                  <span className="error-banner-text">{detailError}</span>
                </div>
              )}

              {!detailLoading && !detailError && selectedEvent && (
                <div className="detail-content">
                  <div className="detail-badge-group">
                    <span className="event-type-badge">{selectedEvent.event_type}</span>
                    <span
                      className={`verification-badge ${(selectedEvent.verification_status || '').toLowerCase()}`}
                    >
                      {selectedEvent.verification_status || 'Unverified'}
                    </span>
                    {selectedEvent.confidence_score !== null &&
                      selectedEvent.confidence_score !== undefined && (
                        <span className="confidence-badge">
                          {selectedEvent.confidence_score}% Confidence
                        </span>
                      )}
                    {selectedEvent.duplicate_of && (
                      <span className="verification-badge duplicate">
                        Duplicate Record
                      </span>
                    )}
                  </div>

                  <div className="drawer-readonly-notice">
                    <Info size={14} aria-hidden="true" />
                    <span>Read-only inspection. Manual overrides are disabled.</span>
                  </div>

                  {selectedEvent.description && selectedEvent.description.trim() && (
                    <div className="detail-section">
                      <h4 className="detail-label">Description</h4>
                      <p className="detail-description">{selectedEvent.description}</p>
                    </div>
                  )}

                  <div className="detail-section">
                    <h4 className="detail-label">Verification & System Metadata</h4>
                    <dl className="detail-grid">
                      <div className="detail-item">
                        <dt>Event ID</dt>
                        <dd className="detail-mono">{selectedEvent.event_id}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Verification Status</dt>
                        <dd>{selectedEvent.verification_status || 'Unverified'}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Confidence Score</dt>
                        <dd>
                          {selectedEvent.confidence_score !== null &&
                          selectedEvent.confidence_score !== undefined
                            ? `${selectedEvent.confidence_score}%`
                            : 'Not scored'}
                        </dd>
                      </div>
                      <div className="detail-item">
                        <dt>Duplicate Of</dt>
                        <dd className={selectedEvent.duplicate_of ? 'detail-mono' : ''}>
                          {selectedEvent.duplicate_of || 'None (Original record)'}
                        </dd>
                      </div>
                      <div className="detail-item">
                        <dt>Data Source</dt>
                        <dd>{selectedEvent.source}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Recorded Time</dt>
                        <dd>{formatTimestamp(selectedEvent.event_timestamp)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Location</dt>
                        <dd>{formatLocation(selectedEvent)}</dd>
                      </div>
                      {selectedEvent.latitude !== null &&
                        selectedEvent.longitude !== null && (
                          <div className="detail-item">
                            <dt>Coordinates</dt>
                            <dd>
                              {selectedEvent.latitude.toFixed(4)}°,{' '}
                              {selectedEvent.longitude.toFixed(4)}°
                            </dd>
                          </div>
                        )}
                    </dl>
                  </div>

                  {hasMeasurements(selectedEvent) && (
                    <div className="detail-section">
                      <h4 className="detail-label">Weather Observations</h4>
                      <dl className="detail-grid">
                        {selectedEvent.rainfall !== null && (
                          <div className="detail-item">
                            <dt>Rainfall</dt>
                            <dd>{selectedEvent.rainfall} mm</dd>
                          </div>
                        )}
                        {selectedEvent.temperature !== null && (
                          <div className="detail-item">
                            <dt>Temperature</dt>
                            <dd>{selectedEvent.temperature} °C</dd>
                          </div>
                        )}
                        {selectedEvent.humidity !== null && (
                          <div className="detail-item">
                            <dt>Humidity</dt>
                            <dd>{selectedEvent.humidity}%</dd>
                          </div>
                        )}
                        {selectedEvent.wind_speed !== null && (
                          <div className="detail-item">
                            <dt>Wind</dt>
                            <dd>
                              {selectedEvent.wind_speed} km/h
                              {selectedEvent.wind_direction !== null &&
                              selectedEvent.wind_direction !== undefined
                                ? ` (${selectedEvent.wind_direction}°)`
                                : ''}
                            </dd>
                          </div>
                        )}
                        {selectedEvent.pressure !== null && (
                          <div className="detail-item">
                            <dt>Pressure</dt>
                            <dd>{selectedEvent.pressure} hPa</dd>
                          </div>
                        )}
                      </dl>
                    </div>
                  )}

                  {(selectedEvent.image_url ||
                    selectedEvent.video_url ||
                    selectedEvent.source_url) && (
                    <div className="detail-section">
                      <h4 className="detail-label">Media & Evidence</h4>
                      <div className="detail-media-links">
                        {selectedEvent.image_url && (
                          <div className="detail-image-box">
                            <a
                              href={selectedEvent.image_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="detail-image-link"
                            >
                              <img
                                src={selectedEvent.image_url}
                                alt={`Observation for ${selectedEvent.event_type}`}
                                className="detail-image-preview"
                              />
                            </a>
                          </div>
                        )}
                        {selectedEvent.video_url && (
                          <a
                            href={selectedEvent.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="detail-link-btn"
                          >
                            <ExternalLink size={14} aria-hidden="true" />
                            <span>Watch Video Footage</span>
                          </a>
                        )}
                        {selectedEvent.source_url && (
                          <a
                            href={selectedEvent.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="detail-link-btn"
                          >
                            <ExternalLink size={14} aria-hidden="true" />
                            <span>View Source Record</span>
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>
        </>
      )}
    </div>
  );
};

export default VerificationPage;
