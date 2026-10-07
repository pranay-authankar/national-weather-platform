# National Weather Big Data Analytics Platform

## API Contract

This document defines the communication contract between the frontend and backend.

The backend collects, processes, verifies, and stores real weather data. The frontend consumes the backend APIs to display weather events, analytics, maps, and citizen reports.

---

## 1. Weather Events

### GET /api/events

Returns weather events collected from supported real data sources.

Optional query parameters:

- state
- district
- city
- event_type
- source
- verification_status
- from
- to
- limit
- offset

Response:

{
  "events": [
    {
      "event_id": "string",
      "source": "string",
      "source_record_id": "string",
      "event_type": "string",
      "description": "string",
      "timestamp": "ISO-8601 datetime",
      "latitude": "number",
      "longitude": "number",
      "city": "string",
      "district": "string",
      "state": "string",
      "temperature": "number|null",
      "rainfall": "number|null",
      "humidity": "number|null",
      "wind_speed": "number|null",
      "wind_direction": "string|null",
      "pressure": "number|null",
      "image_url": "string|null",
      "video_url": "string|null",
      "source_url": "string|null",
      "verification_status": "string",
      "confidence_score": "number|null",
      "duplicate_of": "string|null",
      "created_at": "ISO-8601 datetime"
    }
  ],
  "total": "integer"
}

---

## 2. Single Weather Event

### GET /api/events/{event_id}

Returns complete information about one weather event.

Response fields are the same as the individual event object defined above.

---

## 3. Weather Event Types

The system should support:

- Rainfall
- Heavy Rain
- Thunderstorm
- Flooding
- Heatwave
- Fog
- Dust Storm
- Strong Wind
- Cyclone
- Other

Additional categories may be added when required.

---

## 4. Data Sources

Supported sources may include:

- IMD
- IMD_RSS
- Open_Meteo
- Data_Gov
- Citizen_Report
- Other

The actual source must always be stored.

---

## 5. Verification

Each event that requires verification should contain:

- verification_status
- confidence_score

Possible verification statuses:

- Verified
- Likely
- Unverified
- Rejected
- Duplicate

confidence_score is a number from 0 to 100 representing the system's confidence after comparing available evidence.

The confidence score must not be treated as guaranteed truth.

---

## 6. Duplicate Detection

If an event is identified as a duplicate, duplicate_of should contain the original event ID.

If it is not a duplicate, duplicate_of should be null.

Duplicate detection may consider:

- Location
- Timestamp
- Event type
- Text similarity
- Source information
- Other available evidence

---

## 7. Citizen Weather Reports

### POST /api/reports

Allows a citizen to submit a weather-related report.

Request fields:

- event_type
- description
- latitude
- longitude
- timestamp
- image_url
- video_url

The backend should:

1. Receive the report.
2. Store the report.
3. Determine location information from coordinates.
4. Classify the event if required.
5. Check for possible duplicates.
6. Compare available evidence.
7. Assign verification status and confidence score.

Response:

{
  "event_id": "string",
  "status": "received"
}

---

## 8. Event Statistics

### GET /api/analytics/summary

Returns aggregated statistics for the dashboard.

Response:

{
  "total_events": "integer",
  "verified_events": "integer",
  "unverified_events": "integer",
  "duplicate_events": "integer",
  "event_type_counts": {},
  "state_counts": {},
  "source_counts": {}
}

---

## 9. Map Data

### GET /api/events/map

Returns the event information required for displaying events on the India map.

Response:

{
  "events": [
    {
      "event_id": "string",
      "event_type": "string",
      "latitude": "number",
      "longitude": "number",
      "timestamp": "ISO-8601 datetime",
      "verification_status": "string",
      "confidence_score": "number|null"
    }
  ]
}

---

## 10. API Health Check

### GET /api/health

Checks whether the backend service is running.

Response:

{
  "status": "ok"
}

---

## 11. Date and Time

All API timestamps should use ISO-8601 format.

Example:

YYYY-MM-DDTHH:MM:SSZ

---

## 12. Coordinates

Latitude and longitude must be stored as numeric values.

If location information is unavailable, the value should be null.

---

## 13. Missing Values

If a value is unavailable, return null.

The system must never invent weather values.

---

## 14. Real Data Requirement

The production and hackathon demo must use real data collected from supported sources.

No fabricated weather events should be presented as real events.

Development or test data, if required, must be clearly separated from production data.

---

## 15. Frontend Responsibilities

The frontend is responsible for:

- Dashboard
- India map
- Weather event visualization
- Filters
- Charts
- Event details
- Citizen report form
- Admin and verification interface

---

## 16. Backend Responsibilities

The backend is responsible for:

- Data collection
- Data processing
- Data cleaning
- Data normalization
- AI classification
- Verification
- Duplicate detection
- Database operations
- API responses

---

## 17. API Base URL

During local development:

http://localhost:<backend-port>

The actual backend port will be decided during implementation.

The frontend should store the API base URL in an environment variable instead of hard-coding it throughout the application.