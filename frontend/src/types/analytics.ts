export interface VerificationSummary {
  status: string;
  count: number;
}

export interface EventTypeCountItem {
  event_type: string;
  count: number;
}

export interface SourceCountItem {
  source: string;
  count: number;
}

export interface StateCountItem {
  state: string;
  count: number;
}

export interface DateCountItem {
  date: string;
  count: number;
}

export interface AnalyticsSummary {
  total_events: number;
  verified_events: number;
  likely_events?: number;
  unverified_events: number;
  rejected_events?: number;
  duplicate_events: number;
  verification_breakdown?: VerificationSummary[];
  events_by_verification?: VerificationSummary[];
  events_by_type?: EventTypeCountItem[];
  events_by_source?: SourceCountItem[];
  events_by_state?: StateCountItem[];
  events_over_time?: DateCountItem[];
}
