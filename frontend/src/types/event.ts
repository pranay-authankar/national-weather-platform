export type WeatherEventType =
  | 'Rainfall'
  | 'Heavy Rain'
  | 'Thunderstorm'
  | 'Flooding'
  | 'Heatwave'
  | 'Fog'
  | 'Dust Storm'
  | 'Strong Wind'
  | 'Cyclone'
  | 'Other';

export type WeatherSource =
  | 'IMD'
  | 'IMD_RSS'
  | 'Open_Meteo'
  | 'Data_Gov'
  | 'Citizen_Report'
  | 'Other';

export type VerificationStatus =
  | 'Verified'
  | 'Likely'
  | 'Unverified'
  | 'Rejected'
  | 'Duplicate';

export interface WeatherEvent {
  event_id: string;
  source: string;
  event_type: string;
  description: string | null;
  event_timestamp: string;
  latitude: number | null;
  longitude: number | null;
  city: string | null;
  district: string | null;
  state: string | null;
  temperature: number | null;
  rainfall: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  pressure: number | null;
  image_url: string | null;
  video_url: string | null;
  source_url: string | null;
  verification_status: string;
  confidence_score: number | null;
  duplicate_of: string | null;
  created_at: string;
}

export interface MapWeatherEvent {
  event_id: string;
  latitude: number;
  longitude: number;
  event_type: string;
  source: string;
  event_timestamp: string;
  city: string | null;
  district: string | null;
  state: string | null;
  verification_status: string;
  confidence_score: number | null;
}

export interface PaginationMetadata {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface EventsResponse {
  data: WeatherEvent[];
  pagination: PaginationMetadata;
}

export interface MapEventsResponse {
  data: MapWeatherEvent[];
  count: number;
}

export interface EventFilters {
  state?: string;
  district?: string;
  city?: string;
  event_type?: string;
  source?: string;
  verification_status?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface MapFilters {
  state?: string;
  district?: string;
  city?: string;
  event_type?: string;
  source?: string;
  verification_status?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}
