from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.services.arca import ArcaDisabledError, ArcaNotConfiguredError, get_arca_config
from app.services.arca.wsaa import get_auth_ticket
from app.services.arca.wsfe import WsfeClient
from app.services.arca.wsmtxca import WsmtxcaClient


def service_url(service: str, environment: str) -> str:
    if service == "wsmtxca":
        return "https://fwshomo.afip.gov.ar/wsmtxca/services/MTXCAService" if environment == "homologacion" else "https://serviciosjava.afip.gob.ar/wsmtxca/services/MTXCAService"
    return "https://wswhomo.afip.gov.ar/wsfev1/service.asmx" if environment == "homologacion" else "https://servicios1.afip.gov.ar/wsfev1/service.asmx"


def config_for_service(service: str):
    config = get_arca_config()
    if not config.enabled:
        raise ArcaDisabledError("ARCA no configurado")
    if not config.is_configured:
        raise ArcaNotConfiguredError("ARCA no configurado")

    cache_path = Path(config.token_cache_path)
    return replace(
        config,
        service=service,
        wsfe_url=service_url(service, config.environment),
        token_cache_path=str(cache_path.with_name(f"{cache_path.stem}-{service}{cache_path.suffix}")),
    )


def result_payload(found: bool, result: Any = None, error: Exception | None = None) -> dict[str, Any]:
    if error is not None:
        return {"found": False, "error": f"{type(error).__name__}: {error}"}
    if result is None:
        return {"found": found}
    return {
        "found": found,
        "result": result.result,
        "invoice_number": result.invoice_number,
        "cae": result.cae,
        "cae_expires_at": result.cae_expires_at.isoformat() if result.cae_expires_at else None,
        "observations": result.observations,
        "raw": result.raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta un comprobante en ARCA por WSFEv1 y WSMTXCA.")
    parser.add_argument("--pto-vta", type=int, default=None, help="Punto de venta")
    parser.add_argument("--cbte-tipo", type=int, default=1, help="Tipo de comprobante, 1 = Factura A")
    parser.add_argument("--cbte-nro", type=int, required=True, help="Numero de comprobante")
    args = parser.parse_args()

    base_config = get_arca_config()
    point_of_sale = args.pto_vta or base_config.point_of_sale
    if not point_of_sale:
        raise ArcaNotConfiguredError("Falta punto de venta")

    output: dict[str, Any] = {"query": {"pto_vta": point_of_sale, "cbte_tipo": args.cbte_tipo, "cbte_nro": args.cbte_nro}}

    try:
        wsfe_config = config_for_service("wsfev1")
        wsfe_result = WsfeClient(wsfe_config, get_auth_ticket(wsfe_config)).get_invoice_by_number(point_of_sale, args.cbte_tipo, args.cbte_nro)
        output["wsfev1"] = result_payload(wsfe_result is not None, wsfe_result)
    except Exception as error:
        output["wsfev1"] = result_payload(False, error=error)

    try:
        wsmtxca_config = config_for_service("wsmtxca")
        wsmtxca_result = WsmtxcaClient(wsmtxca_config, get_auth_ticket(wsmtxca_config)).get_invoice_by_number(point_of_sale, args.cbte_tipo, args.cbte_nro)
        output["wsmtxca"] = result_payload(wsmtxca_result is not None, wsmtxca_result)
    except Exception as error:
        output["wsmtxca"] = result_payload(False, error=error)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
