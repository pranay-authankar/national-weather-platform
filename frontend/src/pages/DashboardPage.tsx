import { useState, useEffect, type FC } from 'react';
import { AlertCircle } from 'lucide-react';
import { getEvents } from '../services/eventsApi';
import type { WeatherEvent } from '../types/event';

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

export const DashboardPage: FC = () => {
  const [events, setEvents] = useState<WeatherEvent[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    getEvents({ limit: 10 })
      .then((data) => {
        if (!isMounted) return;
        const fetchedEvents = data?.events ?? [];
        setEvents(fetchedEvents);
        setTotal(data?.total ?? fetchedEvents.length);
        setLoading(false);
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
            <span className="dashboard-state-text">No weather events recorded.</span>
          </div>
        )}

        {!loading && !error && events.length > 0 && (
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
                  <tr key={event.event_id} className="event-row">
                    <td>
                      <span className="event-type-badge">{event.event_type}</span>
                    </td>
                    <td className="event-cell-location">{formatLocation(event)}</td>
                    <td className="event-cell-time">{formatTimestamp(event.timestamp)}</td>
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
        )}
      </div>
    </div>
  );
};

export default DashboardPage;
