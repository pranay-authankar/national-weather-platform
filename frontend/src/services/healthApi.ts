import apiClient from './api';
import type { HealthCheckResponse } from '../types/api';

export async function getHealth(): Promise<HealthCheckResponse> {
  const response = await apiClient.get<HealthCheckResponse>('/api/health');
  return response.data;
}
