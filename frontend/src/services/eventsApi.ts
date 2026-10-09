import apiClient from './api';
import type { EventFilters, EventsResponse, MapEventsResponse, MapFilters, WeatherEvent } from '../types/event';

export async function getEvents(filters?: EventFilters): Promise<EventsResponse> {
  const params: Record<string, string | number> = {};

  if (filters) {
    const keys: (keyof EventFilters)[] = [
      'state',
      'district',
      'city',
      'event_type',
      'source',
      'verification_status',
      'start_time',
      'end_time',
      'page',
      'page_size',
    ];

    for (const key of keys) {
      const val = filters[key];
      if (val !== undefined && val !== null && val !== '') {
        params[key] = val;
      }
    }
  }

  const response = await apiClient.get<EventsResponse>('/api/events', { params });
  return response.data;
}

export async function getEventById(eventId: string): Promise<WeatherEvent> {
  const response = await apiClient.get<WeatherEvent>(`/api/events/${encodeURIComponent(eventId)}`);
  return response.data;
}

export async function getMapEvents(filters?: MapFilters): Promise<MapEventsResponse> {
  const params: Record<string, string | number> = {};

  if (filters) {
    const keys: (keyof MapFilters)[] = [
      'state',
      'district',
      'city',
      'event_type',
      'source',
      'verification_status',
      'start_time',
      'end_time',
      'limit',
    ];

    for (const key of keys) {
      const val = filters[key];
      if (val !== undefined && val !== null && val !== '') {
        params[key] = val;
      }
    }
  }

  const response = await apiClient.get<MapEventsResponse>('/api/events/map', { params });
  return response.data;
}
