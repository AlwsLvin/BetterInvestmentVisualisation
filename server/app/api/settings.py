from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_settings, update_settings
from app.schemas import SettingsModel

router = APIRouter()


@router.get("/settings", response_model=SettingsModel)
def read_settings(settings: SettingsModel = Depends(get_settings)) -> SettingsModel:
    return settings


@router.put("/settings", response_model=SettingsModel)
def write_settings(new: SettingsModel) -> SettingsModel:
    return update_settings(new)
