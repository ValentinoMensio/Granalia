from __future__ import annotations

from .config import ArcaConfig
from .models import ArcaInvoiceRequest


class ArcaDisabledError(RuntimeError):
    pass


class ArcaNotConfiguredError(RuntimeError):
    pass


class ArcaClient:
    def __init__(self, config: ArcaConfig) -> None:
        self.config = config

    def authorize_invoice(self, request: ArcaInvoiceRequest) -> dict[str, object]:
        if not self.config.enabled:
            raise ArcaDisabledError("ARCA no configurado")
        if not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        raise ArcaNotConfiguredError("ARCA no configurado")
