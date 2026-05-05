from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ArcaConfig:
    enabled: bool
    environment: str
    cuit: str
    point_of_sale: int | None
    service: str
    wsaa_url: str
    wsfe_url: str
    cert_path: str
    key_path: str
    key_password: str

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.cuit and self.point_of_sale and self.cert_path and self.key_path and self.service == "wsfev1")


def get_arca_config() -> ArcaConfig:
    point_of_sale = os.getenv("GRANALIA_ARCA_POINT_OF_SALE", "").strip()
    return ArcaConfig(
        enabled=os.getenv("GRANALIA_ARCA_ENABLED", "false").strip().lower() == "true",
        environment=os.getenv("GRANALIA_ARCA_ENV", "homologacion").strip() or "homologacion",
        cuit=os.getenv("GRANALIA_ARCA_CUIT", "").strip(),
        point_of_sale=int(point_of_sale) if point_of_sale.isdigit() else None,
        service=os.getenv("GRANALIA_ARCA_SERVICE", "wsfev1").strip().lower() or "wsfev1",
        wsaa_url=os.getenv("GRANALIA_ARCA_WSAA_URL", "").strip(),
        wsfe_url=os.getenv("GRANALIA_ARCA_WSFE_URL", "").strip(),
        cert_path=os.getenv("GRANALIA_ARCA_CERT_PATH", "").strip(),
        key_path=os.getenv("GRANALIA_ARCA_KEY_PATH", "").strip(),
        key_password=os.getenv("GRANALIA_ARCA_KEY_PASSWORD", "").strip(),
    )
