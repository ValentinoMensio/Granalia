from __future__ import annotations

from app.services.arca import ArcaDisabledError, ArcaNotConfiguredError, get_arca_config
from app.services.arca.wsaa import get_auth_ticket
from app.services.arca.wsfe import WsfeClient, WsfeError
from app.services.arca.wsmtxca import WsmtxcaClient


def main() -> None:
    config = get_arca_config()
    if not config.enabled:
        raise ArcaDisabledError("ARCA no configurado")
    if not config.is_configured:
        raise ArcaNotConfiguredError("ARCA no configurado")

    ticket = get_auth_ticket(config)
    client = WsmtxcaClient(config, ticket) if config.service == "wsmtxca" else WsfeClient(config, ticket)
    points: list[int] = []
    try:
        points = client.get_points_of_sale()
    except WsfeError as error:
        if config.service != "wsfev1" or "Sin Resultados" not in str(error):
            raise
        print(f"Puntos de venta ARCA: sin resultados por FEParamGetPtosVenta ({error})")
    print(f"WSAA OK. Token vence: {ticket.expiration_time}")
    print(f"Servicio: {config.service}")
    if points:
        print(f"Puntos de venta ARCA: {points}")
    if points and config.point_of_sale not in points:
        raise RuntimeError(f"Punto de venta {config.point_of_sale} no habilitado en {config.service}")
    last = client.get_last_authorized(config.point_of_sale, 1)
    print(f"Ultimo Factura A autorizado para PV {config.point_of_sale}: {last}")


if __name__ == "__main__":
    main()
