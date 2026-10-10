import apiClient from './api';
import type {
  CitizenReportPayload,
  CitizenReportResponse,
  MediaUploadResponse,
} from '../types/report';

export async function submitCitizenReport(payload: CitizenReportPayload): Promise<CitizenReportResponse> {
  const response = await apiClient.post<CitizenReportResponse>('/api/reports', payload);
  return response.data;
}

export async function uploadMediaEvidence(file: File): Promise<MediaUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<MediaUploadResponse>('/api/reports/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
}
