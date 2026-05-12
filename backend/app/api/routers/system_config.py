from fastapi import APIRouter, Depends

from app.core.security import require_admin_permission
from app.models.admin import SystemConfig, SystemConfigUpdate
from app.services.system_config_service import get_system_config, set_system_config

router = APIRouter()


@router.get("/admin/system/config", response_model=SystemConfig)
async def read_system_config(
    current_admin: dict = Depends(require_admin_permission("system:manage")),
):
    return await get_system_config()


@router.put("/admin/system/config", response_model=SystemConfig)
async def update_system_config(
    request: SystemConfigUpdate,
    current_admin: dict = Depends(require_admin_permission("system:manage")),
):
    return await set_system_config(request, updated_by=current_admin.get("uid"))
