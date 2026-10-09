import type { WeatherEvent } from './event.ts';

export interface ModerationActionPayload {
  reason: string;
}

export interface ModerationAuditRecord {
  audit_id: string;
  event_id: string;
  previous_status: string;
  new_status: string;
  reason: string;
  moderator_id: string;
  created_at: string;
}

export interface ModerationResponse {
  event_id: string;
  previous_status: string;
  new_status: string;
  reason: string;
  moderator_id: string;
  moderated_at: string;
  event: WeatherEvent;
}

export interface AuditHistoryListResponse {
  data: ModerationAuditRecord[];
  total: number;
  limit: number;
  offset: number;
}
