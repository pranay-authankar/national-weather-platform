import { useState, useEffect, useCallback, type FC, type FormEvent } from 'react';
import { AlertCircle, X, ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react';
import { getEvents, getEventById } from '../services/eventsApi';
import { fetchStates, fetchDistricts, fetchAllDistricts } from '../services/locationsApi';
import type { WeatherEvent, EventFilters, EventsResponse } from '../types/event';
import { EVENT_TYPES, DATA_SOURCES, VERIFICATION_STATUSES } from '../utils/constants';

const PAGE_SIZE = 10;

function formatLocation(event: WeatherEvent): string {
  if (event.city && event.state) {
    return `${event.city}, ${event.state}`;
  }
  if (event.city) {
    return event.city;
  }
  if (event.district && event.state) {
    return `${event.district}, ${event.state}`;
  }
  if (event.state) {
    return event.state;
  }
  if (event.district) {
    return event.district;
  }
  return 'Location unavailable';
}

function formatDetailLocation(event: WeatherEvent): string {
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

function toLocalDayStartIso(dateStr: string): string | undefined {
  if (!dateStr) return undefined;
  const d = new Date(`${dateStr}T00:00:00`);
  return isNaN(d.getTime()) ? undefined : d.toISOString();
}

function toLocalDayEndIso(dateStr: string): string | undefined {
  if (!dateStr) return undefined;
  const d = new Date(`${dateStr}T23:59:59.999`);
  return isNaN(d.getTime()) ? undefined : d.toISOString();
}

export const DashboardPage: FC = () => {
  const [events, setEvents] = useState<WeatherEvent[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [appliedFilters, setAppliedFilters] = useState<EventFilters>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('');
  const [selectedEventType, setSelectedEventType] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  const [knownStates, setKnownStates] = useState<string[]>([]);
  const [districtOptions, setDistrictOptions] = useState<string[]>([]);
  const [districtLoading, setDistrictLoading] = useState<boolean>(false);

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

    setKnownStates((prev) => {
      const combined = new Set([
        ...prev,
        ...fetchedEvents.map((e) => e.state).filter((s): s is string => Boolean(s)),
      ]);
      return Array.from(combined).sort();
    });
  };


  const fetchEvents = useCallback((page: number = 1, filters?: EventFilters) => {
    setLoading(true);
    setError(null);

    getEvents({ page, page_size: PAGE_SIZE, ...filters })
      .then((data) => {
        processFetchedEvents(data);
      })
      .catch(() => {
        setError('Unable to load weather events.');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let isMounted = true;

    getEvents({ page: 1, page_size: PAGE_SIZE })
      .then((data) => {
        if (!isMounted) return;
        processFetchedEvents(data);
      })
      .catch(() => {
        if (!isMounted) return;
        setError('Unable to load weather events.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch authoritative states on mount to populate state options
  useEffect(() => {
    let isMounted = true;
    fetchStates()
      .then((states) => {
        if (!isMounted) return;
        setKnownStates((prev) => Array.from(new Set([...prev, ...states])).sort());
      })
      .catch(() => {
        // Graceful fallback
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Synchronize district options with selected state
  useEffect(() => {
    let isMounted = true;
    async function updateDistrictOptions() {
      const stateQuery = selectedState.trim();
      setDistrictLoading(true);
      try {
        if (stateQuery) {
          const fetched = await fetchDistricts(stateQuery);
          if (!isMounted) return;
          const names = fetched.map((d) => d.district).sort();
          setDistrictOptions(names);
          // If current selected district is not in the new state's districts, reset selection
          setSelectedDistrict((prev) => (prev && !names.includes(prev) ? '' : prev));

        } else {
          const all = await fetchAllDistricts();
          if (!isMounted) return;
          setDistrictOptions(all);
        }
      } catch {
        if (isMounted) setDistrictOptions([]);
      } finally {
        if (isMounted) setDistrictLoading(false);
      }
    }

    updateDistrictOptions();
    return () => {
      isMounted = false;
    };
  }, [selectedState]);

  const handleApplyFilters = (e: FormEvent) => {
    e.preventDefault();

    const filters: EventFilters = {};
    if (selectedState.trim()) filters.state = selectedState.trim();
    if (selectedDistrict.trim()) filters.district = selectedDistrict.trim();
    if (selectedEventType) filters.event_type = selectedEventType;
    if (selectedStatus) filters.verification_status = selectedStatus;
    if (selectedSource) filters.source = selectedSource;
    const startTime = toLocalDayStartIso(dateFrom);
    if (startTime) filters.start_time = startTime;
    const endTime = toLocalDayEndIso(dateTo);
    if (endTime) filters.end_time = endTime;

    setAppliedFilters(filters);
    fetchEvents(1, filters);
  };

  const handleClearFilters = () => {
    setSelectedState('');
    setSelectedDistrict('');
    setSelectedEventType('');
    setSelectedStatus('');
    setSelectedSource('');
    setDateFrom('');
    setDateTo('');

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
    appliedFilters.state ||
    appliedFilters.district ||
    appliedFilters.event_type ||
    appliedFilters.verification_status ||
    appliedFilters.source ||
    appliedFilters.start_time ||
    appliedFilters.end_time
  );

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h2 className="page-title">National Weather Dashboard</h2>
        <p className="page-subtitle">Live weather events across India.</p>
      </div>

      <div className="dashboard-events-section">
        <div className="dashboard-section-header">
          <h3 className="section-title">Recent Weather Events</h3>
          {!loading && !error && (
            <span className="section-count">
              {total} {total === 1 ? 'event' : 'events'}
            </span>
          )}
        </div>

        <form className="dashboard-filter-bar" onSubmit={handleApplyFilters}>
          <div className="filter-row filter-row-primary">
            <span className="filter-label">Filters</span>

            <input
              type="text"
              className="filter-control filter-input"
              placeholder="State"
              aria-label="Filter by state"
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              list="known-states-list"
            />
            <datalist id="known-states-list">
              {knownStates.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>

            <select
              className="filter-control filter-select"
              aria-label="Filter by district"
              value={selectedDistrict}
              onChange={(e) => setSelectedDistrict(e.target.value)}
              disabled={districtLoading}
            >
              <option value="">
                {districtLoading
                  ? 'Loading districts...'
                  : districtOptions.length === 0
                  ? (selectedState.trim() ? 'No districts for state' : 'No districts available')
                  : 'District (All)'}
              </option>
              {districtOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>

            <select
              className="filter-control filter-select"
              aria-label="Filter by event type"
              value={selectedEventType}
              onChange={(e) => setSelectedEventType(e.target.value)}
            >
              <option value="">Event Type (All)</option>
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>

            <select
              className="filter-control filter-select"
              aria-label="Filter by verification status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="">Status (All)</option>
              {VERIFICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>

            <select
              className="filter-control filter-select"
              aria-label="Filter by data source"
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
            >
              <option value="">Source (All)</option>
              {DATA_SOURCES.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-row filter-row-secondary">
            <div className="filter-date-inputs">
              <input
                type="date"
                className="filter-control filter-date"
                aria-label="Date from"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
              <span className="filter-date-sep" aria-hidden="true">to</span>
              <input
                type="date"
                className="filter-control filter-date"
                aria-label="Date to"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>

            <div className="filter-actions">
              <button type="submit" className="filter-btn filter-btn-apply">
                Apply
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
            <span className="dashboard-state-text">Loading events...</span>
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
                ? 'No weather events match the selected filters.'
                : 'No weather events recorded.'}
            </span>
          </div>
        )}

        {!loading && !error && events.length > 0 && (
          <>
            <div className="events-table-container">
              <table className="events-table">
                <thead>
                  <tr>
                    <th scope="col">Event Type</th>
                    <th scope="col">Location</th>
                    <th scope="col">Timestamp</th>
                    <th scope="col">Source</th>
                    <th scope="col">Verification Status</th>
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
                      aria-label={`View details for ${event.event_type} in ${formatLocation(event)}`}
                    >
                      <td>
                        <span className="event-type-badge">{event.event_type}</span>
                      </td>
                      <td className="event-cell-location">{formatLocation(event)}</td>
                      <td className="event-cell-time">{formatTimestamp(event.event_timestamp)}</td>
                      <td className="event-cell-source">{event.source}</td>
                      <td>
                        <span
                          className={`verification-badge ${(event.verification_status || '').toLowerCase()}`}
                        >
                          {event.verification_status || 'Unverified'}
                        </span>
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
                Event Details
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
                  </div>

                  {selectedEvent.description && selectedEvent.description.trim() && (
                    <div className="detail-section">
                      <h4 className="detail-label">Description</h4>
                      <p className="detail-description">{selectedEvent.description}</p>
                    </div>
                  )}

                  <div className="detail-section">
                    <h4 className="detail-label">Event Information</h4>
                    <dl className="detail-grid">
                      <div className="detail-item">
                        <dt>Event ID</dt>
                        <dd className="detail-mono">{selectedEvent.event_id}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Location</dt>
                        <dd>{formatDetailLocation(selectedEvent)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Recorded Time</dt>
                        <dd>{formatTimestamp(selectedEvent.event_timestamp)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Data Source</dt>
                        <dd>{selectedEvent.source}</dd>
                      </div>
                      {selectedEvent.duplicate_of && (
                        <div className="detail-item">
                          <dt>Duplicate Of</dt>
                          <dd className="detail-mono">{selectedEvent.duplicate_of}</dd>
                        </div>
                      )}
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

export default DashboardPage;
