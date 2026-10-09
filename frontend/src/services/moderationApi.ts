import axios from 'axios';
import apiClient from './api.ts';
import type {
  AuditHistoryListResponse,
  ModerationActionPayload,
  ModerationAuditRecord,
  ModerationResponse,
} from '../types/moderation';

/**
 * Build authentication headers using the in-memory admin token.
 * Never persists or leaks token values into logs or global storage.
 */
function getAuthHeaders(adminToken?: string): Record<string, string> {
  const token = adminToken?.trim();
  if (!token) {
    throw new Error('Admin authentication token is required.');
  }
  return {
    Authorization: `Bearer ${token}`,
    'X-Admin-Token': token,
  };
}

/**
 * Safely extract user-facing error message from Axios errors or exceptions
 * without exposing sensitive tokens or internal stack traces.
 */
export function extractErrorMessage(err: unknown, fallback: string = 'Moderation action failed'): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d))).join('; ');
    }
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
    if (err.response?.status === 401) {
      return 'Unauthorized: Invalid admin authentication credentials.';
    }
    if (err.response?.status === 403) {
      return 'Forbidden: Insufficient administrative privileges.';
    }
    if (err.response?.status === 404) {
      return 'Weather report record not found.';
    }
    if (err.response?.status === 503) {
      return 'Service temporarily unavailable. Please try again later.';
    }
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

/**
 * Admin Verify: transition report to Verified (100% confidence).
 * Rejects duplicate records per backend constraint.
 */
export async function verifyReport(
  eventId: string,
  reason: string,
  adminToken: string
): Promise<ModerationResponse> {
  const cleanReason = reason.trim();
  if (cleanReason.length < 3) {
    throw new Error('Moderation reason must be at least 3 characters long.');
  }

  const payload: ModerationActionPayload = { reason: cleanReason };
  const headers = getAuthHeaders(adminToken);

  const response = await apiClient.post<ModerationResponse>(
    `/api/admin/reports/${encodeURIComponent(eventId)}/verify`,
    payload,
    { headers }
  );
  return response.data;
}

/**
 * Admin Reject: transition report to Rejected (0% confidence).
 */
export async function rejectReport(
  eventId: string,
  reason: string,
  adminToken: string
): Promise<ModerationResponse> {
  const cleanReason = reason.trim();
  if (cleanReason.length < 3) {
    throw new Error('Moderation reason must be at least 3 characters long.');
  }

  const payload: ModerationActionPayload = { reason: cleanReason };
  const headers = getAuthHeaders(adminToken);

  const response = await apiClient.post<ModerationResponse>(
    `/api/admin/reports/${encodeURIComponent(eventId)}/reject`,
    payload,
    { headers }
  );
  return response.data;
}

/**
 * Admin Restore: restore a previously Rejected report to Unverified (35% baseline).
 * Backend permits only Rejected reports to be restored for reassessment.
 */
export async function restoreReport(
  eventId: string,
  reason: string,
  adminToken: string
): Promise<ModerationResponse> {
  const cleanReason = reason.trim();
  if (cleanReason.length < 3) {
    throw new Error('Moderation reason must be at least 3 characters long.');
  }

  const payload: ModerationActionPayload = { reason: cleanReason };
  const headers = getAuthHeaders(adminToken);

  const response = await apiClient.post<ModerationResponse>(
    `/api/admin/reports/${encodeURIComponent(eventId)}/restore`,
    payload,
    { headers }
  );
  return response.data;
}

/**
 * Get chronological moderation audit history for a single event.
 */
export async function getReportAuditHistory(
  eventId: string,
  adminToken: string
): Promise<ModerationAuditRecord[]> {
  const headers = getAuthHeaders(adminToken);
  const response = await apiClient.get<ModerationAuditRecord[]>(
    `/api/admin/reports/${encodeURIComponent(eventId)}/audit-history`,
    { headers }
  );
  return response.data;
}

/**
 * Query paginated global moderation audit records across all events.
 */
export async function getGlobalAuditHistory(
  params?: { event_id?: string; limit?: number; offset?: number },
  adminToken?: string
): Promise<AuditHistoryListResponse> {
  const headers = getAuthHeaders(adminToken);
  const queryParams: Record<string, string | number> = {};

  if (params?.event_id) queryParams.event_id = params.event_id;
  if (params?.limit !== undefined) queryParams.limit = params.limit;
  if (params?.offset !== undefined) queryParams.offset = params.offset;

  const response = await apiClient.get<AuditHistoryListResponse>('/api/admin/audit-history', {
    headers,
    params: queryParams,
  });
  return response.data;
}
