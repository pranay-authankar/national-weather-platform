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
  Lock,
  Unlock,
  RotateCcw,
  History,
  Shield,
  Loader2,
  Check,
} from 'lucide-react';
import { getEvents, getEventById } from '../services/eventsApi';
import { getAnalyticsSummary } from '../services/analyticsApi';
import {
  verifyReport,
  rejectReport,
  restoreReport,
  getReportAuditHistory,
  extractErrorMessage,
} from '../services/moderationApi';
import type { WeatherEvent, EventFilters, EventsResponse } from '../types/event';
import type { AnalyticsSummary } from '../types/analytics';
import type { ModerationAuditRecord } from '../types/moderation';
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
  // Event queue and metrics state
  const [events, setEvents] = useState<WeatherEvent[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [appliedFilters, setAppliedFilters] = useState<EventFilters>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);

  // Filters state
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [selectedEventType, setSelectedEventType] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<string>('');

  // Selected event inspection drawer
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<WeatherEvent | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Admin Token & Security State (Held strictly in volatile React memory for current page session)
  const [adminToken, setAdminToken] = useState<string>('');
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [tempTokenInput, setTempTokenInput] = useState<string>('');

  // Moderation Action Modal state
  const [activeAction, setActiveAction] = useState<'verify' | 'reject' | 'restore' | null>(null);
  const [moderationReason, setModerationReason] = useState<string>('');
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Notification Toast state
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Audit History state for selected event
  const [auditHistory, setAuditHistory] = useState<ModerationAuditRecord[]>([]);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);

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

  const fetchSummary = useCallback(() => {
    getAnalyticsSummary()
      .then((data) => {
        setSummary(data);
      })
      .catch(() => {
        // Non-critical fallback
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
        setError('Unable to load verification data.');
        setLoading(false);
      });

    fetchSummary();

    return () => {
      isMounted = false;
    };
  }, [fetchSummary]);

  const loadAuditHistory = useCallback((eventId: string, token: string) => {
    if (!token.trim()) {
      setAuditHistory([]);
      return;
    }
    setAuditLoading(true);
    setAuditError(null);

    getReportAuditHistory(eventId, token)
      .then((data) => {
        setAuditHistory(data);
        setAuditLoading(false);
      })
      .catch((err) => {
        setAuditError(extractErrorMessage(err, 'Could not retrieve audit history.'));
        setAuditLoading(false);
      });
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
    fetchEvents(currentPage - 1, appliedFilters);
  };

  const handleNextPage = () => {
    const maxPages = totalPages > 0 ? totalPages : 1;
    if (currentPage >= maxPages || loading) return;
    fetchEvents(currentPage + 1, appliedFilters);
  };

  const handleSelectEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    setSelectedEvent(null);
    setDetailLoading(true);
    setDetailError(null);
    setAuditHistory([]);
    setAuditError(null);

    getEventById(eventId)
      .then((data) => {
        setSelectedEvent(data);
        setDetailLoading(false);
        if (adminToken.trim()) {
          loadAuditHistory(eventId, adminToken);
        }
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
    setAuditHistory([]);
    setActiveAction(null);
  }, []);

  useEffect(() => {
    if (!selectedEventId) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeAction) {
          setActiveAction(null);
        } else if (isAuthModalOpen) {
          setIsAuthModalOpen(false);
        } else {
          handleCloseDetail();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selectedEventId, activeAction, isAuthModalOpen, handleCloseDetail]);

  // Handle setting / clearing in-memory admin token
  const handleSaveToken = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = tempTokenInput.trim();
    if (!trimmed) return;
    setAdminToken(trimmed);
    setIsAuthModalOpen(false);
    setTempTokenInput('');
    setToastMessage({
      type: 'success',
      text: 'Admin mode active for this page session. Token stored in memory only.',
    });

    if (selectedEventId) {
      loadAuditHistory(selectedEventId, trimmed);
    }
  };

  const handleClearToken = () => {
    setAdminToken('');
    setAuditHistory([]);
    setToastMessage({
      type: 'success',
      text: 'Admin session locked. Token cleared from memory.',
    });
  };

  // Moderation action initiation
  const handleInitiateAction = (action: 'verify' | 'reject' | 'restore') => {
    setActiveAction(action);
    setModerationReason('');
    setActionError(null);
  };

  // Moderation action submission
  const handleSubmitModeration = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedEvent || !activeAction) return;

    const trimmedReason = moderationReason.trim();
    if (trimmedReason.length < 3) {
      setActionError('Moderation reason must be at least 3 non-whitespace characters long.');
      return;
    }

    const tokenToUse = adminToken.trim() || tempTokenInput.trim();
    if (!tokenToUse) {
      setActionError('Admin token is required to execute moderation decisions.');
      return;
    }

    // If token entered in modal, save to memory
    if (!adminToken.trim() && tempTokenInput.trim()) {
      setAdminToken(tempTokenInput.trim());
      setTempTokenInput('');
    }

    setActionLoading(true);
    setActionError(null);

    try {
      let result;
      if (activeAction === 'verify') {
        result = await verifyReport(selectedEvent.event_id, trimmedReason, tokenToUse);
      } else if (activeAction === 'reject') {
        result = await rejectReport(selectedEvent.event_id, trimmedReason, tokenToUse);
      } else {
        result = await restoreReport(selectedEvent.event_id, trimmedReason, tokenToUse);
      }

      setToastMessage({
        type: 'success',
        text: `Report ${result.event_id.slice(0, 8)}... successfully transitioned to '${result.new_status}'.`,
      });

      // Update state and refresh all data
      setActiveAction(null);
      setModerationReason('');
      setSelectedEvent(result.event);

      // Refresh list, metrics, and audit history
      fetchEvents(currentPage, appliedFilters);
      fetchSummary();
      loadAuditHistory(selectedEvent.event_id, tokenToUse);
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to apply moderation decision.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Rule constraints for action button permissions
  const isDuplicate = Boolean(
    selectedEvent?.duplicate_of || selectedEvent?.verification_status === 'Duplicate'
  );
  const isAlreadyVerified = selectedEvent?.verification_status === 'Verified';
  const isAlreadyRejected = selectedEvent?.verification_status === 'Rejected';

  const canVerify = !isAlreadyVerified && !isDuplicate;
  const canReject = !isAlreadyRejected;
  const canRestore = isAlreadyRejected;

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
        <h2 className="page-title">Event Verification & Moderation</h2>
        <p className="page-subtitle">
          Review, verify, reject, and restore weather reports with complete administrative audit trails.
        </p>
      </div>

      {/* Admin Authorization Status Bar */}
      <div className="admin-auth-bar" role="region" aria-label="Admin Access Control">
        <div className="admin-auth-status">
          {adminToken ? (
            <span className="admin-status-badge active">
              <Unlock size={14} aria-hidden="true" />
              <span>Admin Mode Active</span>
            </span>
          ) : (
            <span className="admin-status-badge locked">
              <Lock size={14} aria-hidden="true" />
              <span>Admin Mode Locked (Read-Only)</span>
            </span>
          )}
          <span className="admin-security-note">
            {adminToken
              ? 'Token held in volatile browser session memory only. Never written to storage or URLs.'
              : 'Authenticate with your admin token to enable Verify, Reject, Restore, and Audit History.'}
          </span>
        </div>

        <div className="admin-auth-actions">
          {adminToken ? (
            <button
              type="button"
              className="btn-admin-auth lock"
              onClick={handleClearToken}
              aria-label="Lock Admin Mode and clear session token"
            >
              <Lock size={13} aria-hidden="true" />
              <span>Lock / Clear Token</span>
            </button>
          ) : (
            <button
              type="button"
              className="btn-admin-auth unlock"
              onClick={() => {
                setTempTokenInput('');
                setIsAuthModalOpen(true);
              }}
              aria-label="Authenticate as Admin"
            >
              <Unlock size={13} aria-hidden="true" />
              <span>Authenticate as Admin</span>
            </button>
          )}
        </div>
      </div>

      {/* Notification Toast Banner */}
      {toastMessage && (
        <div
          className={`moderation-toast ${toastMessage.type}`}
          role={toastMessage.type === 'error' ? 'alert' : 'status'}
        >
          <div className="moderation-toast-content">
            {toastMessage.type === 'success' ? (
              <Check size={16} aria-hidden="true" />
            ) : (
              <AlertCircle size={16} aria-hidden="true" />
            )}
            <span>{toastMessage.text}</span>
          </div>
          <button
            type="button"
            className="moderation-toast-close"
            onClick={() => setToastMessage(null)}
            aria-label="Dismiss message"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      )}

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
          <div className="summary-card-sub">Pending review</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Rejected</span>
            <XCircle size={16} className="summary-card-icon rejected" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{rejectedCount}</div>
          <div className="summary-card-sub">Refuted / spam records</div>
        </div>

        <div className="summary-card">
          <div className="summary-card-header">
            <span className="summary-card-label">Duplicate</span>
            <Layers size={16} className="summary-card-icon duplicate" aria-hidden="true" />
          </div>
          <div className="summary-card-value">{duplicateCount}</div>
          <div className="summary-card-sub">Linked duplicates</div>
        </div>
      </div>

      {/* Verification Queue Section */}
      <div className="dashboard-events-section verification-events-section">
        <div className="dashboard-section-header">
          <h3 className="section-title">Moderation Queue</h3>
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
            <span className="dashboard-state-text">Loading moderation queue...</span>
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
                ? 'No reports match the selected filters.'
                : 'No reports currently awaiting moderation.'}
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
                    <th scope="col">Status</th>
                    <th scope="col">Confidence</th>
                    <th scope="col">Credibility</th>
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
                      aria-label={`Inspect report ${event.event_id}: ${event.event_type} in ${formatLocation(event)}`}
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
                        {event.credibility_score !== null && event.credibility_score !== undefined ? (
                          <span
                            className={`credibility-pill ${
                              event.credibility_score >= 70
                                ? 'high'
                                : event.credibility_score >= 40
                                ? 'medium'
                                : 'suspicious'
                            }`}
                          >
                            <Shield size={11} aria-hidden="true" />
                            <span>{event.credibility_score}%</span>
                          </span>
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
                          aria-label={`Moderate report ${event.event_id}`}
                        >
                          Review
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
                disabled={currentPage >= totalPages || loading}
                aria-label="Next page"
              >
                <span>Next</span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Event Inspection & Moderation Drawer */}
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
            aria-labelledby="drawer-title"
          >
            <div className="drawer-header">
              <div className="drawer-title-group">
                <span className="drawer-eyebrow">Report Inspection & Moderation</span>
                <h3 id="drawer-title" className="drawer-title">
                  {selectedEvent ? selectedEvent.event_type : 'Report Details'}
                </h3>
              </div>
              <button
                type="button"
                className="drawer-close-btn"
                onClick={handleCloseDetail}
                aria-label="Close report details"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="drawer-body">
              {detailLoading && (
                <div className="detail-loading-box">
                  <div className="loading-spinner" aria-hidden="true" />
                  <p className="detail-loading-text">Loading report details...</p>
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

                  {/* Administrative Moderation Controls */}
                  <div className="moderation-actions-section">
                    <div className="moderation-actions-header">
                      <span className="moderation-actions-title">Administrative Actions</span>
                      {!adminToken && (
                        <span className="moderation-disabled-hint">
                          <Lock size={12} style={{ display: 'inline', marginRight: 4 }} />
                          Auth required
                        </span>
                      )}
                    </div>

                    <div className="moderation-btn-group">
                      <button
                        type="button"
                        className="btn-mod-action verify"
                        disabled={!canVerify}
                        onClick={() => handleInitiateAction('verify')}
                        title={
                          isDuplicate
                            ? 'Cannot mark duplicate record as Verified'
                            : isAlreadyVerified
                            ? 'Report is already Verified'
                            : 'Mark report as Verified (100% confidence)'
                        }
                      >
                        <CheckCircle2 size={16} aria-hidden="true" />
                        <span>Verify</span>
                      </button>

                      <button
                        type="button"
                        className="btn-mod-action reject"
                        disabled={!canReject}
                        onClick={() => handleInitiateAction('reject')}
                        title={
                          isAlreadyRejected
                            ? 'Report is already Rejected'
                            : 'Mark report as Rejected (0% confidence)'
                        }
                      >
                        <XCircle size={16} aria-hidden="true" />
                        <span>Reject</span>
                      </button>

                      <button
                        type="button"
                        className="btn-mod-action restore"
                        disabled={!canRestore}
                        onClick={() => handleInitiateAction('restore')}
                        title={
                          !isAlreadyRejected
                            ? 'Only Rejected reports can be restored to Unverified for reassessment'
                            : 'Restore rejected report to Unverified (35% baseline)'
                        }
                      >
                        <RotateCcw size={16} aria-hidden="true" />
                        <span>Restore</span>
                      </button>
                    </div>

                    {isDuplicate && (
                      <p className="moderation-disabled-hint">
                        ⚠️ <strong>Duplicate restriction:</strong> This event is linked to an existing report (duplicate_of: {selectedEvent.duplicate_of}). Duplicate events cannot be verified while retaining duplicate association.
                      </p>
                    )}
                  </div>

                  {/* Credibility Analysis Details */}
                  {(selectedEvent.credibility_score !== undefined ||
                    selectedEvent.credibility_status ||
                    selectedEvent.source_trust_score !== undefined) && (
                    <div className="detail-section">
                      <h4 className="detail-label">Credibility Analysis</h4>
                      <dl className="detail-grid">
                        <div className="detail-item">
                          <dt>Credibility Status</dt>
                          <dd>
                            {selectedEvent.credibility_status ? (
                              <span
                                className={`credibility-pill ${
                                  selectedEvent.credibility_status === 'Likely'
                                    ? 'high'
                                    : selectedEvent.credibility_status === 'Suspicious'
                                    ? 'suspicious'
                                    : 'medium'
                                }`}
                              >
                                {selectedEvent.credibility_status}
                              </span>
                            ) : (
                              'Not assessed'
                            )}
                          </dd>
                        </div>
                        <div className="detail-item">
                          <dt>Credibility Score</dt>
                          <dd>
                            {selectedEvent.credibility_score !== null &&
                            selectedEvent.credibility_score !== undefined
                              ? `${selectedEvent.credibility_score}%`
                              : '—'}
                          </dd>
                        </div>
                        <div className="detail-item">
                          <dt>Source Trust Score</dt>
                          <dd>
                            {selectedEvent.source_trust_score !== null &&
                            selectedEvent.source_trust_score !== undefined
                              ? `${selectedEvent.source_trust_score}%`
                              : 'Standard'}
                          </dd>
                        </div>
                      </dl>

                      {selectedEvent.credibility_reasons &&
                        selectedEvent.credibility_reasons.length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)' }}>
                              Evaluation Reasons:
                            </span>
                            <ul style={{ margin: '4px 0 0 16px', fontSize: 12, color: 'var(--text-secondary)' }}>
                              {selectedEvent.credibility_reasons.map((reason, idx) => (
                                <li key={idx}>{reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                    </div>
                  )}

                  {/* Audit Trail Section */}
                  <div className="detail-section audit-history-section">
                    <div className="audit-history-header">
                      <h4 className="detail-label">Moderation Audit Trail</h4>
                      {adminToken && (
                        <button
                          type="button"
                          className="filter-btn-clear"
                          style={{ fontSize: 11, padding: '2px 8px' }}
                          onClick={() => loadAuditHistory(selectedEvent.event_id, adminToken)}
                          title="Refresh audit history"
                        >
                          <History size={12} style={{ display: 'inline', marginRight: 4 }} />
                          Refresh
                        </button>
                      )}
                    </div>

                    {!adminToken ? (
                      <div className="audit-locked-prompt">
                        <span>Admin authorization required to view audit trail.</span>
                        <button
                          type="button"
                          className="table-action-btn"
                          onClick={() => setIsAuthModalOpen(true)}
                        >
                          Unlock
                        </button>
                      </div>
                    ) : auditLoading ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                        <Loader2 size={14} className="btn-icon-spin" />
                        <span>Loading audit history...</span>
                      </div>
                    ) : auditError ? (
                      <div className="detail-error-banner" style={{ margin: 0 }}>
                        <AlertCircle size={14} />
                        <span>{auditError}</span>
                      </div>
                    ) : auditHistory.length === 0 ? (
                      <p className="audit-empty-message">No administrative decisions recorded for this report yet.</p>
                    ) : (
                      <div className="audit-history-list">
                        {auditHistory.map((record) => (
                          <div key={record.audit_id} className="audit-history-item">
                            <div className="audit-item-meta">
                              <span className="audit-transition-flow">
                                <span>{record.previous_status}</span>
                                <span className="arrow">→</span>
                                <span style={{ color: 'var(--primary)' }}>{record.new_status}</span>
                              </span>
                              <span className="audit-item-moderator">
                                mod: {record.moderator_id}
                              </span>
                            </div>
                            <div className="audit-item-reason">
                              "{record.reason}"
                            </div>
                            <div className="audit-item-time">
                              {formatTimestamp(record.created_at)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Description & Report Content */}
                  {selectedEvent.description && selectedEvent.description.trim() && (
                    <div className="detail-section">
                      <h4 className="detail-label">Description</h4>
                      <p className="detail-description">{selectedEvent.description}</p>
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="detail-section">
                    <h4 className="detail-label">System Metadata</h4>
                    <dl className="detail-grid">
                      <div className="detail-item">
                        <dt>Event ID</dt>
                        <dd className="detail-mono">{selectedEvent.event_id}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Data Source</dt>
                        <dd>{selectedEvent.source}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Duplicate Of</dt>
                        <dd className={selectedEvent.duplicate_of ? 'detail-mono' : ''}>
                          {selectedEvent.duplicate_of || 'None (Original record)'}
                        </dd>
                      </div>
                      <div className="detail-item">
                        <dt>Observed Time</dt>
                        <dd>{formatTimestamp(selectedEvent.event_timestamp)}</dd>
                      </div>
                      <div className="detail-item">
                        <dt>Location</dt>
                        <dd>{formatLocation(selectedEvent)}</dd>
                      </div>
                      {selectedEvent.latitude !== null && selectedEvent.longitude !== null && (
                        <div className="detail-item">
                          <dt>Coordinates</dt>
                          <dd>
                            {selectedEvent.latitude.toFixed(4)}°, {selectedEvent.longitude.toFixed(4)}°
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>

                  {/* Weather Observations */}
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
                              {selectedEvent.wind_direction !== null && selectedEvent.wind_direction !== undefined
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

                  {/* Media & External Evidence */}
                  {(selectedEvent.image_url || selectedEvent.video_url || selectedEvent.source_url) && (
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

      {/* Moderation Action Modal Dialog */}
      {activeAction && selectedEvent && (
        <div className="moderation-modal-overlay" role="dialog" aria-modal="true">
          <div className="moderation-modal-card">
            <div className="moderation-modal-header">
              <h4 className="moderation-modal-title">
                {activeAction === 'verify' && <CheckCircle2 size={18} style={{ color: '#16a34a' }} />}
                {activeAction === 'reject' && <XCircle size={18} style={{ color: '#dc2626' }} />}
                {activeAction === 'restore' && <RotateCcw size={18} style={{ color: '#ea580c' }} />}
                <span>
                  {activeAction === 'verify'
                    ? 'Verify Weather Report'
                    : activeAction === 'reject'
                    ? 'Reject Weather Report'
                    : 'Restore Report to Unverified'}
                </span>
              </h4>
              <button
                type="button"
                className="moderation-modal-close"
                onClick={() => setActiveAction(null)}
                aria-label="Close dialog"
                disabled={actionLoading}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmitModeration}>
              <div className="moderation-modal-body">
                <div className={`moderation-modal-info ${activeAction}`}>
                  <Info size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <strong>Target Report:</strong> {selectedEvent.event_type} in {formatLocation(selectedEvent)} ({selectedEvent.event_id.slice(0, 8)}...)
                    <br />
                    {activeAction === 'verify' && (
                      <span>This will mark the observation as <strong>Verified</strong> (100% confidence). Note that duplicate records cannot be verified.</span>
                    )}
                    {activeAction === 'reject' && (
                      <span>This will mark the observation as <strong>Rejected</strong> (0% confidence).</span>
                    )}
                    {activeAction === 'restore' && (
                      <span>This will restore the rejected report to <strong>Unverified</strong> (35% baseline confidence) for re-evaluation.</span>
                    )}
                  </div>
                </div>

                {/* If token not set in memory, provide input directly */}
                {!adminToken && (
                  <div className="moderation-form-group">
                    <label className="moderation-form-label" htmlFor="modal-admin-token">
                      <span>Admin API Token</span>
                      <span className="moderation-form-label-sub">Stored in session memory only</span>
                    </label>
                    <input
                      id="modal-admin-token"
                      type="password"
                      className="moderation-input"
                      placeholder="Enter ADMIN_API_KEY..."
                      value={tempTokenInput}
                      onChange={(e) => setTempTokenInput(e.target.value)}
                      required
                      autoComplete="off"
                    />
                  </div>
                )}

                {/* Mandatory Moderation Reason */}
                <div className="moderation-form-group">
                  <label className="moderation-form-label" htmlFor="moderation-reason">
                    <span>Justification Reason <span style={{ color: '#dc2626' }}>*</span></span>
                    <span className="moderation-form-label-sub">
                      Minimum 3 characters (recorded in audit log)
                    </span>
                  </label>
                  <textarea
                    id="moderation-reason"
                    className="moderation-textarea"
                    placeholder="Provide detailed reason for this decision (e.g. Verified with ground station radar data; Duplicate false report)..."
                    value={moderationReason}
                    onChange={(e) => setModerationReason(e.target.value)}
                    required
                    disabled={actionLoading}
                  />
                  <div
                    className={`moderation-char-counter ${
                      moderationReason.trim().length > 0 && moderationReason.trim().length < 3
                        ? 'invalid'
                        : ''
                    }`}
                  >
                    {moderationReason.trim().length} / 3 min characters
                  </div>
                </div>

                {actionError && (
                  <div className="moderation-modal-error" role="alert">
                    <AlertCircle size={15} style={{ flexShrink: 0 }} />
                    <span>{actionError}</span>
                  </div>
                )}
              </div>

              <div className="moderation-modal-footer">
                <button
                  type="button"
                  className="btn-modal-cancel"
                  onClick={() => setActiveAction(null)}
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className={`btn-modal-submit ${activeAction}`}
                  disabled={
                    actionLoading ||
                    moderationReason.trim().length < 3 ||
                    (!adminToken && !tempTokenInput.trim())
                  }
                >
                  {actionLoading ? (
                    <>
                      <Loader2 size={14} className="btn-icon-spin" />
                      <span>Processing...</span>
                    </>
                  ) : (
                    <span>
                      {activeAction === 'verify'
                        ? 'Confirm Verification'
                        : activeAction === 'reject'
                        ? 'Confirm Rejection'
                        : 'Confirm Restore'}
                    </span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Standalone Admin Auth Dialog */}
      {isAuthModalOpen && (
        <div className="moderation-modal-overlay" role="dialog" aria-modal="true">
          <div className="moderation-modal-card" style={{ maxWidth: 440 }}>
            <div className="moderation-modal-header">
              <h4 className="moderation-modal-title">
                <Lock size={16} />
                <span>Admin Authentication</span>
              </h4>
              <button
                type="button"
                className="moderation-modal-close"
                onClick={() => setIsAuthModalOpen(false)}
                aria-label="Close authentication dialog"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveToken}>
              <div className="moderation-modal-body">
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.45 }}>
                  Enter your administrative token to unlock moderation controls and audit trail access.
                </p>

                <div className="moderation-form-group">
                  <label className="moderation-form-label" htmlFor="standalone-admin-token">
                    <span>Admin Token</span>
                  </label>
                  <input
                    id="standalone-admin-token"
                    type="password"
                    className="moderation-input"
                    placeholder="Enter ADMIN_API_KEY..."
                    value={tempTokenInput}
                    onChange={(e) => setTempTokenInput(e.target.value)}
                    required
                    autoFocus
                    autoComplete="off"
                  />
                </div>

                <div
                  style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    backgroundColor: '#f8fafc',
                    padding: '8px 10px',
                    borderRadius: 4,
                    border: '1px solid var(--border-subtle)',
                    lineHeight: 1.4,
                  }}
                >
                  🔒 <strong>In-Memory Guarantee:</strong> Your token is kept purely in volatile component memory and will not be stored in localStorage, sessionStorage, cookies, or URL queries. Refreshing the browser will automatically clear the token.
                </div>
              </div>

              <div className="moderation-modal-footer">
                <button
                  type="button"
                  className="btn-modal-cancel"
                  onClick={() => setIsAuthModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-modal-submit verify"
                  disabled={!tempTokenInput.trim()}
                >
                  <span>Unlock Admin Mode</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default VerificationPage;
