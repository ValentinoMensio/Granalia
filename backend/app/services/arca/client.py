from __future__ import annotations

from pathlib import Path

from .config import ArcaConfig
from .models import ArcaAuthorizationResult, ArcaInvoiceRequest
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

    def authorize_invoice(self, request: ArcaInvoiceRequest, cbte_number: int | None = None) -> dict[str, object]:
        if not self.config.enabled:
            raise ArcaDisabledError("ARCA no configurado")
        if not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        if not Path(self.config.cert_path).exists() or not Path(self.config.key_path).exists():
            raise ArcaNotConfiguredError("ARCA no configurado")
        if self.config.service == "wsfev1":
            return self._authorize_wsfe(request, cbte_number=cbte_number)
        raise ArcaNotConfiguredError("ARCA no configurado")

    def get_next_number(self, request: ArcaInvoiceRequest) -> int:
        if not self.config.enabled or not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        try:
            wsfe = WsfeClient(self.config, get_auth_ticket(self.config))
            return wsfe.get_last_authorized(request.point_of_sale, request.cbte_tipo) + 1
        except (WsaaError, WsfeTechnicalError) as error:
            raise ArcaTechnicalError(str(error)) from error
        except WsfeError as error:
            raise ArcaRejectedError(str(error)) from error

    def get_receiver_iva_conditions(self) -> list[dict[str, object]]:
        if not self.config.enabled or not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        try:
            return WsfeClient(self.config, get_auth_ticket(self.config)).get_receiver_iva_conditions()
        except (WsaaError, WsfeTechnicalError) as error:
            raise ArcaTechnicalError(str(error)) from error
        except WsfeError as error:
            raise ArcaRejectedError(str(error)) from error

    def recover_invoice(self, request: ArcaInvoiceRequest, cbte_number: int) -> dict[str, object] | None:
        if not self.config.enabled or not self.config.is_configured:
            raise ArcaNotConfiguredError("ARCA no configurado")
        try:
            result = WsfeClient(self.config, get_auth_ticket(self.config)).get_invoice_by_number(request.point_of_sale, request.cbte_tipo, cbte_number)
        except (WsaaError, WsfeTechnicalError) as error:
            raise ArcaTechnicalError(str(error)) from error
        except WsfeError as error:
            message = str(error)
            if "no existe" in message.lower() or "sin resultados" in message.lower():
                return None
            raise ArcaRejectedError(message) from error
        if not result or result.result != "A" or not result.cae:
            return None
        return self._result_payload(result)

    def _result_payload(self, result: ArcaAuthorizationResult) -> dict[str, object]:
        return {
            "result": result.result,
            "invoice_number": result.invoice_number,
            "cae": result.cae,
            "cae_expires_at": result.cae_expires_at,
            "observations": result.observations,
            "raw": result.raw,
        }

    def _authorize_wsfe(self, request: ArcaInvoiceRequest, *, cbte_number: int | None = None) -> dict[str, object]:
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
            next_number = cbte_number or wsfe.get_last_authorized(request.point_of_sale, request.cbte_tipo) + 1
            if self.config.dry_run:
                return {
                    "result": "DRY_RUN",
                    "invoice_number": next_number,
                    "cae": None,
                    "cae_expires_at": None,
                    "observations": [{"Code": "DRY_RUN", "Msg": "Validacion ARCA OK; no se llamo FECAESolicitar"}],
                    "raw": {"dry_run": True, "points_of_sale": points_of_sale, "next_number": next_number},
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
        return self._result_payload(result)
