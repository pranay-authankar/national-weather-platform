"""
API Router for Authoritative Administrative Locations.
Provides endpoints for retrieving official Indian states and districts with verified coordinates.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from services.location_service import (
    AUTHORITATIVE_LOCATIONS,
    get_all_states,
    get_districts_for_state,
)

router = APIRouter(prefix="/api/locations", tags=["Locations"])


class DistrictLocationResponse(BaseModel):
    """District name and authoritative geographical coordinates."""
    district: str = Field(..., description="Official administrative district name.")
    latitude: float = Field(..., description="Verified latitude coordinate.")
    longitude: float = Field(..., description="Verified longitude coordinate.")


@router.get(
    "/states",
    response_model=List[str],
    status_code=status.HTTP_200_OK,
    summary="List Authoritative Indian States and UTs",
    description="Returns a sorted list of all 36 official Indian States and Union Territories.",
)
def list_states() -> List[str]:
    return get_all_states()


@router.get(
    "/districts",
    response_model=List[DistrictLocationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Districts for a State",
    description="Returns verified districts and their official coordinates for the specified state.",
)
def list_districts(
    state: str = Query(..., description="Name of the state to retrieve districts for."),
) -> List[DistrictLocationResponse]:
    districts = get_districts_for_state(state)
    if not districts:
        # Check if state exists
        all_states = [s.lower() for s in get_all_states()]
        if state.strip().lower() not in all_states:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"State '{state}' not found in authoritative administrative database.",
            )
        return []
    return [DistrictLocationResponse(**d) for d in districts]


@router.get(
    "",
    response_model=Dict[str, List[DistrictLocationResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get Full Administrative Locations Hierarchy",
    description="Returns all states mapped to their verified districts and coordinates.",
)
def get_all_locations_hierarchy() -> Dict[str, List[DistrictLocationResponse]]:
    return {
        state: [DistrictLocationResponse(**d) for d in districts]
        for state, districts in sorted(AUTHORITATIVE_LOCATIONS.items())
    }


class DetectedLocationResponse(BaseModel):
    """Resolved authoritative location for given coordinates."""
    state: str = Field(..., description="Authoritative Indian state or Union Territory.")
    district: str = Field(..., description="Authoritative administrative district.")
    latitude: float = Field(..., description="Observed/detected latitude.")
    longitude: float = Field(..., description="Observed/detected longitude.")
    source: str = Field(default="nearest_district", description="Resolution method (reverse_geocoding or nearest_district).")


@router.get(
    "/detect",
    response_model=DetectedLocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect Authoritative State and District from GPS Coordinates",
    description="Resolves latitude and longitude coordinates to an authoritative Indian state and district.",
)
async def detect_location(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude coordinate between -90.0 and 90.0 degrees."),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude coordinate between -180.0 and 180.0 degrees."),
) -> DetectedLocationResponse:
    from services.location_service import detect_location_from_coordinates

    detected = await detect_location_from_coordinates(latitude, longitude)
    if not detected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not resolve an authoritative Indian state and district for the provided coordinates.",
        )
    return DetectedLocationResponse(**detected)

