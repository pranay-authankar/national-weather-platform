import apiClient from './api';
import type { AnalyticsSummary } from '../types/analytics';

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  const response = await apiClient.get<AnalyticsSummary>('/api/analytics/summary');
  return response.data;
}
