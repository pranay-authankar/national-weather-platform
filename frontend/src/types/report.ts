export interface CitizenReportPayload {
  event_type: string;
  description: string;
  state?: string | null;
  district?: string | null;
  city?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  timestamp?: string;
  image_url?: string | null;
  video_url?: string | null;
}

export interface CitizenReportResponse {
  event_id: string;
  status: string;
}

export interface MediaUploadResponse {
  url: string;
  relative_url: string;
  filename: string;
  media_type: 'image' | 'video';
  content_type: string;
  size_bytes: number;
}

export interface LocationDistrict {
  district: string;
  latitude: number;
  longitude: number;
}
