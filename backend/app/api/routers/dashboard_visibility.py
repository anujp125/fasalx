from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_admin, require_admin_permission
from app.models.dashboard_visibility import (
    DashboardComponentToggleRequest,
    DashboardComponentToggleResponse,
    DashboardVisibilityResponse,
    DashboardVisibilityUpdate,
)
from app.services.dashboard_visibility_service import (
    get_dashboard_visibility,
    set_dashboard_visibility,
    toggle_dashboard_component,
)

router = APIRouter()


@router.get("/dashboard/visibility", response_model=DashboardVisibilityResponse)
async def get_public_dashboard_visibility():
    return await get_dashboard_visibility()


@router.get("/admin/dashboard/visibility", response_model=DashboardVisibilityResponse)
async def get_admin_dashboard_visibility(
    current_admin: dict = Depends(require_admin_permission("dashboard:manage")),
):
    return await get_dashboard_visibility()


@router.put("/admin/dashboard/visibility", response_model=DashboardVisibilityResponse)
async def update_admin_dashboard_visibility(
    request: DashboardVisibilityUpdate,
    current_admin: dict = Depends(require_admin_permission("dashboard:manage")),
):
    return await set_dashboard_visibility(
        request.components,
        updated_by=current_admin.get("uid"),
    )


@router.patch("/admin/dashboard/visibility/toggle", response_model=DashboardComponentToggleResponse)
async def toggle_admin_dashboard_component(
    request: DashboardComponentToggleRequest,
    current_admin: dict = Depends(require_admin_permission("dashboard:manage")),
):
    try:
        config = await toggle_dashboard_component(
            component=request.component,
            visible=request.visible,
            updated_by=current_admin.get("uid"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = "shown" if request.visible else "hidden"
    return DashboardComponentToggleResponse(
        message=f"Dashboard component '{request.component}' is now {state}.",
        config=config,
    )
