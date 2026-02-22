from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Any, List

import yaml
from pydantic import BaseModel, Field, field_validator

from .config import settings


def _tenants_dir() -> Path:
    return Path(settings.TENANTS_DIR).resolve()


class ThemeConfig(BaseModel):
    accent_color: Optional[str] = None
    accent2_color: Optional[str] = None
    font_family: Optional[str] = None
    logo_url: Optional[str] = None
    background_url: Optional[str] = None


class ContentConfig(BaseModel):
    headline: Optional[str] = None
    subheadline: Optional[str] = None
    panel_what_next_title: Optional[str] = None
    panel_what_next_text: Optional[str] = None
    panel_tip_title: Optional[str] = None
    panel_tip_text: Optional[str] = None
    privacy_line: Optional[str] = None
    success_message: Optional[str] = None


class ServiceItem(BaseModel):
    key: str
    label: str
    description: Optional[str] = None
    eta: Optional[str] = "Vandaag"
    enabled: bool = True


class TenantConfig(BaseModel):
    tenant_id: str
    business_name: str = ""
    notify_email: Optional[str] = None

    whatsapp_enabled: bool = False
    whatsapp_number: Optional[str] = None

    booking_url: Optional[str] = None

    services: List[ServiceItem] = Field(default_factory=list)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)

    tenant_admin_username: Optional[str] = None
    tenant_admin_password_hash: Optional[str] = None

    @field_validator("tenant_id")
    @classmethod
    def _tid(cls, v: str) -> str:
        return (v or "").strip()


def tenant_path(tenant_id: str) -> Path:
    return _tenants_dir() / f"{tenant_id}.yaml"


def load_tenant(tenant_id: str) -> TenantConfig:
    path = tenant_path(tenant_id)
    if not path.exists():
        raise FileNotFoundError(f"Tenant file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TenantConfig.model_validate(data)


def save_tenant(cfg: TenantConfig) -> None:
    tdir = _tenants_dir()
    tdir.mkdir(parents=True, exist_ok=True)
    path = tenant_path(cfg.tenant_id)

    payload = cfg.model_dump(exclude_none=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def enabled_services(cfg: TenantConfig) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in cfg.services or []:
        if s.enabled:
            out.append(s.model_dump(exclude_none=True))
    return out