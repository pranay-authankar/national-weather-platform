export interface CitizenReportPayload {
  event_type: string;
  description: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  image_url?: string | null;
  video_url?: string | null;
}

export interface CitizenReportResponse {
  event_id: string;
  status: string;
}
