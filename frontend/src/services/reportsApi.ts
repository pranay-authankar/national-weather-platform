import apiClient from './api';
import type { CitizenReportPayload, CitizenReportResponse } from '../types/report';

export async function submitCitizenReport(payload: CitizenReportPayload): Promise<CitizenReportResponse> {
  const response = await apiClient.post<CitizenReportResponse>('/api/reports', payload);
  return response.data;
}
