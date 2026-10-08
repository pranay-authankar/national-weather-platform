import type { WeatherEventType, WeatherSource, VerificationStatus } from '../types/event';

export const EVENT_TYPES: readonly WeatherEventType[] = [
  'Rainfall',
  'Heavy Rain',
  'Thunderstorm',
  'Flooding',
  'Heatwave',
  'Fog',
  'Dust Storm',
  'Strong Wind',
  'Cyclone',
  'Other',
];

export const DATA_SOURCES: readonly WeatherSource[] = [
  'IMD',
  'IMD_RSS',
  'Open_Meteo',
  'Data_Gov',
  'Citizen_Report',
  'Other',
];

export const VERIFICATION_STATUSES: readonly VerificationStatus[] = [
  'Verified',
  'Likely',
  'Unverified',
  'Rejected',
  'Duplicate',
];
