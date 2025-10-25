from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.deps import get_current_tenant
from app.models.appointment import (
    AppointmentRequest,
    AppointmentResponse,
    AppointmentUpdateRequest,
)
from app.models.auth import TenantClaims
from app.services.google_calendar import (
    create_appointment,
    delete_appointment,
    update_appointment,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: AppointmentRequest,
    tenant: TenantClaims = Depends(get_current_tenant),
) -> AppointmentResponse:
    try:
        return create_appointment(tenant, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to create Google Calendar event",
        ) from exc


@router.patch(
    "/{event_id}",
    response_model=AppointmentResponse,
)
async def update_event(
    payload: AppointmentUpdateRequest,
    event_id: str = Path(..., description="Google Calendar event identifier."),
    tenant: TenantClaims = Depends(get_current_tenant),
) -> AppointmentResponse:
    try:
        return update_appointment(tenant, event_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to update Google Calendar event",
        ) from exc


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_endpoint(
    event_id: str,
    calendar_id: str = "primary",
    tenant: TenantClaims = Depends(get_current_tenant),
) -> None:
    try:
        delete_appointment(tenant, event_id, calendar_id=calendar_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to delete Google Calendar event",
        ) from exc
