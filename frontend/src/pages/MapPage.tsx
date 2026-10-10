import { useState, useEffect, useCallback, type FC, type FormEvent } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AlertCircle, X, ExternalLink } from 'lucide-react';
import { getMapEvents, getEventById } from '../services/eventsApi';
import type { MapWeatherEvent, WeatherEvent, MapFilters } from '../types/event';
import { EVENT_TYPES, DATA_SOURCES, VERIFICATION_STATUSES } from '../utils/constants';

const INDIA_CENTER: [number, number] = [21.8, 78.9];
const INDIA_BOUNDS: [[number, number], [number, number]] = [
  [6.0, 66.0],
  [38.0, 99.0],
];
const MIN_ZOOM = 4;
const MAX_ZOOM = 18;
const INITIAL_ZOOM = 5;

function getEventCode(eventType: string): string {
  switch (eventType) {
    case 'Rainfall':
      return 'RF';
    case 'Heavy Rain':
      return 'HR';
    case 'Thunderstorm':
      return 'TS';
    case 'Flooding':
      return 'FL';
    case 'Heatwave':
      return 'HW';
    case 'Fog':
      return 'FG';
    case 'Dust Storm':
      return 'DS';
    case 'Strong Wind':
      return 'SW';
    case 'Cyclone':
      return 'CY';
    default:
      return 'WX';
  }
}

function createMapMarkerIcon(eventType: string, status: string): L.DivIcon {
  const statusClass = (status || 'unverified').toLowerCase();
  const code = getEventCode(eventType);

  return L.divIcon({
    className: 'custom-weather-pin-container',
    html: `
      <div class="weather-map-pin ${statusClass}" title="${eventType} (${status})">
        <span class="pin-code">${code}</span>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  });
}

function formatMapLocation(event: MapWeatherEvent): string {
  if (typeof event.latitude === 'number' && typeof event.longitude === 'number') {
    return `${event.latitude.toFixed(4)}°, ${event.longitude.toFixed(4)}°`;
  }
  return 'Coordinates unavailable';
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

export const MapPage: FC = () => {
  const [events, setEvents] = useState<MapWeatherEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedEventType, setSelectedEventType] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedState, setSelectedState] = useState<string>('');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('');
  const [selectedCity, setSelectedCity] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  const [knownStates, setKnownStates] = useState<string[]>([]);
  const [knownDistricts, setKnownDistricts] = useState<string[]>([]);
  const [knownCities, setKnownCities] = useState<string[]>([]);

  const [isFiltered, setIsFiltered] = useState<boolean>(false);

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<WeatherEvent | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const processFetchedEvents = (fetchedEvents: MapWeatherEvent[]) => {
    // Strictly exclude rejected reports from all map markers and regional summaries
    const validEvents = fetchedEvents.filter((e) => e.verification_status !== 'Rejected');
    setEvents(validEvents);
    setLoading(false);

    setKnownStates((prev) => {
      const combined = new Set([
        ...prev,
        ...validEvents.map((e) => e.state).filter((s): s is string => Boolean(s)),
      ]);
      return Array.from(combined).sort();
    });
    setKnownDistricts((prev) => {
      const combined = new Set([
        ...prev,
        ...validEvents.map((e) => e.district).filter((d): d is string => Boolean(d)),
      ]);
      return Array.from(combined).sort();
    });
    setKnownCities((prev) => {
      const combined = new Set([
        ...prev,
        ...validEvents.map((e) => e.city).filter((c): c is string => Boolean(c)),
      ]);
      return Array.from(combined).sort();
    });
  };

  const fetchMapData = useCallback((filters?: MapFilters) => {
    setLoading(true);
    setError(null);

    getMapEvents(filters)
      .then((data) => {
        processFetchedEvents(data?.data ?? []);
      })
      .catch(() => {
        setError('Unable to load map data.');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let isMounted = true;

    getMapEvents()
      .then((data) => {
        if (!isMounted) return;
        processFetchedEvents(data?.data ?? []);
      })
      .catch(() => {
        if (!isMounted) return;
        setError('Unable to load map data.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleApplyFilters = (e: FormEvent) => {
    e.preventDefault();

    const filters: MapFilters = {};
    if (selectedEventType) filters.event_type = selectedEventType;
    if (selectedSource) filters.source = selectedSource;
    if (selectedStatus) filters.verification_status = selectedStatus;
    if (selectedState) filters.state = selectedState;
    if (selectedDistrict) filters.district = selectedDistrict;
    if (selectedCity) filters.city = selectedCity;
    const startTime = toLocalDayStartIso(dateFrom);
    if (startTime) filters.start_time = startTime;
    const endTime = toLocalDayEndIso(dateTo);
    if (endTime) filters.end_time = endTime;

    const hasAnyFilter = Object.keys(filters).length > 0;
    setIsFiltered(hasAnyFilter);

    fetchMapData(filters);
  };

  const handleClearFilters = () => {
    setSelectedEventType('');
    setSelectedSource('');
    setSelectedStatus('');
    setSelectedState('');
    setSelectedDistrict('');
    setSelectedCity('');
    setDateFrom('');
    setDateTo('');
    setIsFiltered(false);

    fetchMapData();
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

  const validEvents = events.filter(
    (e) =>
      typeof e.latitude === 'number' &&
      typeof e.longitude === 'number' &&
      !isNaN(e.latitude) &&
      !isNaN(e.longitude) &&
      e.latitude !== null &&
      e.longitude !== null
  );

  return (
    <div className="map-page">
      <div className="page-header map-page-header">
        <div className="page-header-titles">
          <h2 className="page-title">Live Weather & Disaster Map</h2>
          <p className="page-subtitle">
            Geographical distribution of real-time weather events across India with coordinate-level tracking.
          </p>
        </div>
        {!loading && !error && (
          <div className="map-header-meta">
            <span className="section-count">
              {validEvents.length} mapped {validEvents.length === 1 ? 'event' : 'events'}
            </span>
          </div>
        )}
      </div>

      <form className="dashboard-filter-bar map-filter-bar" onSubmit={handleApplyFilters}>
        <div className="filter-row filter-row-primary">
          <span className="filter-label">Map Filters</span>

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

          <select
            className="filter-control filter-select"
            aria-label="Filter by verification status"
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
          >
            <option value="">All Verification Statuses</option>
            {VERIFICATION_STATUSES.filter((status) => status !== 'Rejected').map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>

          <select
            className="filter-control filter-select"
            aria-label="Filter by state"
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
          >
            <option value="">All States</option>
            {knownStates.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>

          <select
            className="filter-control filter-select"
            aria-label="Filter by district"
            value={selectedDistrict}
            onChange={(e) => setSelectedDistrict(e.target.value)}
          >
            <option value="">All Districts</option>
            {knownDistricts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>

          <select
            className="filter-control filter-select"
            aria-label="Filter by city"
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value)}
          >
            <option value="">All Cities</option>
            {knownCities.map((c) => (
              <option key={c} value={c}>
                {c}
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
        <div className="dashboard-state-box loading map-status-alert">
          <span className="dashboard-state-text">Loading weather events...</span>
        </div>
      )}

      {!loading && error && (
        <div className="dashboard-error-banner map-status-alert" role="alert">
          <AlertCircle size={15} className="error-banner-icon" aria-hidden="true" />
          <span className="error-banner-text">{error}</span>
        </div>
      )}

      {!loading && !error && validEvents.length === 0 && (
        <div className="dashboard-state-box empty map-status-alert">
          <span className="dashboard-state-text">
            {isFiltered
              ? 'No weather events match the selected filters.'
              : 'No mapped weather events available.'}
          </span>
        </div>
      )}

      <div className="map-container-wrapper">
        <MapContainer
          center={INDIA_CENTER}
          zoom={INITIAL_ZOOM}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          maxBounds={INDIA_BOUNDS}
          maxBoundsViscosity={0.8}
          scrollWheelZoom={true}
          className="leaflet-map-element"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {validEvents.map((event) => (
            <Marker
              key={event.event_id}
              position={[event.latitude as number, event.longitude as number]}
              icon={createMapMarkerIcon(event.event_type, event.verification_status)}
            >
              <Popup>
                <div className="map-popup">
                  <div className="map-popup-badges">
                    <span className="event-type-badge">{event.event_type}</span>
                    <span
                      className={`verification-badge ${(event.verification_status || '').toLowerCase()}`}
                    >
                      {event.verification_status || 'Unverified'}
                    </span>
                  </div>

                  <div className="map-popup-meta">
                    <div className="map-popup-location">{formatMapLocation(event)}</div>
                    <div className="map-popup-time">{formatTimestamp(event.event_timestamp)}</div>
                    {event.confidence_score !== null &&
                      event.confidence_score !== undefined && (
                        <div className="map-popup-confidence">
                          {event.confidence_score}% Confidence
                        </div>
                      )}
                  </div>

                  <button
                    type="button"
                    className="map-popup-btn"
                    onClick={() => handleSelectEvent(event.event_id)}
                  >
                    View Full Details
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>

        <div className="map-legend-card" aria-label="Verification status legend">
          <span className="legend-title">Verification</span>
          <div className="legend-items">
            <span className="legend-item">
              <span className="legend-dot verified"></span> Verified
            </span>
            <span className="legend-item">
              <span className="legend-dot likely"></span> Likely
            </span>
            <span className="legend-item">
              <span className="legend-dot unverified"></span> Unverified
            </span>
            <span className="legend-item">
              <span className="legend-dot rejected"></span> Rejected
            </span>
            <span className="legend-item">
              <span className="legend-dot duplicate"></span> Duplicate
            </span>
          </div>
        </div>
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
            aria-labelledby="map-drawer-title"
          >
            <div className="drawer-header">
              <h3 id="map-drawer-title" className="drawer-title">
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

export default MapPage;
