export interface AnalyticsSummary {
  total_events: number;
  verified_events: number;
  unverified_events: number;
  duplicate_events: number;
  event_type_counts: Record<string, number>;
  state_counts: Record<string, number>;
  source_counts: Record<string, number>;
}
