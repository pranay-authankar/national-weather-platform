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
  source_record_id: string;
  event_type: string;
  description: string;
  timestamp: string;
  latitude: number | null;
  longitude: number | null;
  city: string;
  district: string;
  state: string;
  temperature: number | null;
  rainfall: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: string | null;
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
  event_type: string;
  latitude: number | null;
  longitude: number | null;
  timestamp: string;
  verification_status: string;
  confidence_score: number | null;
}

export interface EventsResponse {
  events: WeatherEvent[];
  total: number;
}

export interface MapEventsResponse {
  events: MapWeatherEvent[];
}

export interface EventFilters {
  state?: string;
  district?: string;
  city?: string;
  event_type?: string;
  source?: string;
  verification_status?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}
