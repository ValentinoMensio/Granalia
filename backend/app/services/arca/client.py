from __future__ import annotations

from pathlib import Path

from .config import ArcaConfig
from .models import ArcaInvoiceRequest
from .wsaa import WsaaError, get_auth_ticket
from .wsfe import WsfeClient, WsfeError, WsfeTechnicalError


class ArcaDisabledError(RuntimeError):
    pass


class ArcaNotConfiguredError(RuntimeError):
    pass


class ArcaRejectedError(RuntimeError):
    pass


class ArcaTechnicalError(RuntimeError):
    pass


class ArcaClient:
    def __init__(self, config: ArcaConfig) -> None:
        self.config = config

    def authorize_invoice(self, request: ArcaInvoiceRequest) -> dict[str, object]:
        if not self.config.enabled:
            raise ArcaDisabledError("ARCA no configurado")
        if not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        if not Path(self.config.cert_path).exists() or not Path(self.config.key_path).exists():
            raise ArcaNotConfiguredError("ARCA no configurado")
        if self.config.service == "wsfev1":
            return self._authorize_wsfe(request)
        raise ArcaNotConfiguredError("ARCA no configurado")

    def _authorize_wsfe(self, request: ArcaInvoiceRequest) -> dict[str, object]:
        try:
            wsfe = WsfeClient(self.config, get_auth_ticket(self.config))
            points_of_sale: list[int] = []
            try:
                points_of_sale = wsfe.get_points_of_sale()
            except WsfeError as error:
                if "Sin Resultados" not in str(error):
                    raise
            if points_of_sale and request.point_of_sale not in points_of_sale:
                raise ArcaRejectedError(f"Punto de venta {request.point_of_sale} no habilitado en ARCA")
            last_authorized = wsfe.get_last_authorized(request.point_of_sale, request.cbte_tipo)
            next_number = last_authorized + 1
            if self.config.dry_run:
                return {
                    "result": "DRY_RUN",
                    "invoice_number": next_number,
                    "cae": None,
                    "cae_expires_at": None,
                    "observations": [{"Code": "DRY_RUN", "Msg": "Validacion ARCA OK; no se llamo FECAESolicitar"}],
                    "raw": {"dry_run": True, "points_of_sale": points_of_sale, "last_authorized": last_authorized, "next_number": next_number},
                }
            try:
                result = wsfe.request_cae(request, next_number)
            except WsfeTechnicalError as error:
                reconciled_last = wsfe.get_last_authorized(request.point_of_sale, request.cbte_tipo)
                if reconciled_last >= next_number:
                    recovered = wsfe.get_invoice_by_number(request.point_of_sale, request.cbte_tipo, next_number)
                    if recovered and recovered.cae:
                        result = recovered
                    else:
                        raise ArcaTechnicalError("Error tecnico ARCA; comprobante encontrado pero no conciliado") from error
                else:
                    raise ArcaTechnicalError("Error tecnico ARCA; no reintentar sin conciliar") from error
        except (WsaaError, WsfeTechnicalError) as error:
            raise ArcaTechnicalError(str(error)) from error
        except WsfeError as error:
            raise ArcaRejectedError(str(error)) from error

        if result.result != "A" or not result.cae:
            observations = "; ".join(str(item.get("Msg") or item.get("Code")) for item in result.observations)
            raise ArcaRejectedError(observations or "ARCA rechazo la solicitud")
        return {
            "result": result.result,
            "invoice_number": result.invoice_number,
            "cae": result.cae,
            "cae_expires_at": result.cae_expires_at,
            "observations": result.observations,
            "raw": result.raw,
        }
