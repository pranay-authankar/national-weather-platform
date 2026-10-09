"""
Main FastAPI application for National Weather Big Data Analytics Platform.
"""

from contextlib import asynccontextmanager
import sys
from pathlib import Path
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend root directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.open_meteo import (
    fetch_open_meteo_weather,
    OpenMeteoTimeoutError,
    OpenMeteoRequestError,
    OpenMeteoAPIError,
    OpenMeteoResponseError,
)
from services.weather_event_service import (
    ingest_open_meteo_weather,
)
from services.scheduler_service import (
    get_scheduler_status,
    start_scheduler,
    stop_scheduler,
)
from database import (
    check_database_connection,
    get_db_config,
)
from routers.analytics import router as analytics_router
from routers.events import router as events_router
from routers.map import router as map_router
from routers.reports import router as reports_router
from routers.data_gov import router as data_gov_router
from routers.moderation import router as moderation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background weather ingestion scheduler
    start_scheduler()
    try:
        yield
    finally:
        # Shutdown: Cleanly terminate scheduler
        stop_scheduler()


app = FastAPI(
    title="National Weather Big Data Analytics Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register routers
app.include_router(reports_router)
app.include_router(analytics_router)
app.include_router(map_router)
app.include_router(events_router)
app.include_router(data_gov_router)
app.include_router(moderation_router)



@app.get("/api/health")
def health_check() -> Dict[str, str]:
    """
    Health check endpoint returning application status.
    """
    return {"status": "ok"}


@app.get("/api/scheduler/status")
def scheduler_status() -> Dict[str, Any]:
    """
    Retrieve operational health and status metadata for the Open-Meteo background ingestion scheduler.
    """
    return get_scheduler_status()


@app.get("/api/database/health")
def database_health() -> Dict[str, Any]:
    """
    Temporary endpoint to verify PostgreSQL connectivity via Supabase Session Pooler.
    Executes a lightweight SELECT 1 query to confirm connectivity without leaking secrets.
    """
    try:
        check_database_connection()
        config = get_db_config()
        return {
            "status": "ok",
            "database": "connected",
            "host": config["host"],
            "port": config["port"],
            "database_name": config["dbname"],
            "user": config["user"],
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unexpected error while connecting to PostgreSQL.",
        )


@app.get("/api/weather/open-meteo")
async def get_open_meteo_weather(
    latitude: float = Query(..., description="Latitude coordinate between -90.0 and 90.0"),
    longitude: float = Query(..., description="Longitude coordinate between -180.0 and 180.0"),
) -> Dict[str, Any]:
    """
    Temporary endpoint to fetch and verify live weather data from Open-Meteo
    for dynamic latitude and longitude coordinates.
    """
    # Validate coordinate ranges
    if not (-90.0 <= latitude <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid latitude: {latitude}. Must be between -90.0 and 90.0 degrees.",
        )

    if not (-180.0 <= longitude <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid longitude: {longitude}. Must be between -180.0 and 180.0 degrees.",
        )

    try:
        weather_data = await fetch_open_meteo_weather(
            latitude=latitude,
            longitude=longitude,
        )

        return {
            "source": "open-meteo",
            "latitude": weather_data.get("latitude"),
            "longitude": weather_data.get("longitude"),
            "elevation": weather_data.get("elevation"),
            "timezone": weather_data.get("timezone"),
            "current_units": weather_data.get("current_units"),
            "current": weather_data.get("current"),
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OpenMeteoTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        )
    except (OpenMeteoRequestError, OpenMeteoAPIError, OpenMeteoResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected internal server error: {exc}",
        )


@app.post("/api/test/ingest-open-meteo")
async def test_ingest_open_meteo(
    latitude: float = Query(21.25, description="Latitude coordinate (default: 21.25 for Raipur)"),
    longitude: float = Query(81.63, description="Longitude coordinate (default: 81.63 for Raipur)"),
    city: str = Query("Raipur", description="City name"),
    state: str = Query("Chhattisgarh", description="State name"),
) -> Dict[str, Any]:
    """
    Temporary endpoint to fetch live weather data for a single location from Open-Meteo,
    normalize the payload into the weather_events schema, and insert the record into PostgreSQL.
    """
    if not (-90.0 <= latitude <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid latitude: {latitude}. Must be between -90.0 and 90.0 degrees.",
        )

    if not (-180.0 <= longitude <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid longitude: {longitude}. Must be between -180.0 and 180.0 degrees.",
        )

    try:
        inserted_event = await ingest_open_meteo_weather(
            latitude=latitude,
            longitude=longitude,
            city=city,
            state=state,
        )

        return {
            "status": "success",
            "message": "Weather event successfully ingested into PostgreSQL weather_events table.",
            "event_id": inserted_event["event_id"],
            "weather_code": inserted_event.get("weather_code"),
            "classified_event_type": inserted_event["event_type"],
            "inserted_values": {
                "source": inserted_event["source"],
                "source_record_id": inserted_event["source_record_id"],
                "event_type": inserted_event["event_type"],
                "event_timestamp": inserted_event["event_timestamp"],
                "latitude": inserted_event["latitude"],
                "longitude": inserted_event["longitude"],
                "city": inserted_event["city"],
                "state": inserted_event["state"],
                "temperature": inserted_event["temperature"],
                "rainfall": inserted_event["rainfall"],
                "humidity": inserted_event["humidity"],
                "wind_speed": inserted_event["wind_speed"],
                "wind_direction": inserted_event["wind_direction"],
                "pressure": inserted_event["pressure"],
                "verification_status": inserted_event["verification_status"],
                "confidence_score": inserted_event["confidence_score"],
                "created_at": inserted_event["created_at"],
            },
        }

    except OpenMeteoTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        )
    except (OpenMeteoRequestError, OpenMeteoAPIError, OpenMeteoResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest weather event: {exc}",
        )
