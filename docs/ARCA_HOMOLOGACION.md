# ARCA Homologacion

## Variables requeridas

```bash
GRANALIA_ARCA_ENABLED=true
GRANALIA_ARCA_ENV=homologacion
GRANALIA_ARCA_SERVICE=wsmtxca
GRANALIA_ARCA_CUIT=20225790346
GRANALIA_ARCA_POINT_OF_SALE=<punto_de_venta_wsmtxca>
GRANALIA_ARCA_CERT_PATH=/ruta/al/certificado.crt
GRANALIA_ARCA_KEY_PATH=/ruta/a/la/private.key
GRANALIA_ARCA_KEY_PASSWORD=<si_aplica>
GRANALIA_INVOICE_AUTH_PASSWORD_HASH=<hash_bcrypt>
```

URLs por defecto en homologacion:

```bash
GRANALIA_ARCA_WSAA_URL=https://wsaahomo.afip.gov.ar/ws/services/LoginCms
GRANALIA_ARCA_SERVICE_URL=https://fwshomo.afip.gov.ar/wsmtxca/services/MTXCAService
```

## Diagnostico WSAA/WSMTXCA

Desde la raiz del repo:

```bash
PYTHONPATH=backend python3 backend/scripts/arca_homologacion.py
```

Debe validar:

- WSAA `loginCms` con token/sign.
- `consultarPuntosVenta` contiene `GRANALIA_ARCA_POINT_OF_SALE`.
- `consultarUltimoComprobanteAutorizado` responde para Factura A (`codigoTipoComprobante=1`).

## Pruebas de CAE

Crear facturas fiscales desde la UI y usar `Autorizar en ARCA` en Historial.

Casos minimos:

- Factura A con IVA 21%.
- Factura A con IVA 10,5%.
- Factura A mixta con ambas alicuotas.
- Rechazo por CUIT invalido.
- Timeout/error tecnico: el backend consulta `consultarUltimoComprobanteAutorizado` y, si el numero quedo autorizado, intenta recuperar con `consultarComprobante` antes de permitir reintento.

## Servicio

Los metodos usados por defecto son de `wsmtxca`: `consultarPuntosVenta`, `consultarUltimoComprobanteAutorizado`, `consultarComprobante` y `autorizarComprobante`.
El parametro `GRANALIA_ARCA_WSFE_URL` sigue soportado por compatibilidad, pero para WSMTXCA se recomienda `GRANALIA_ARCA_SERVICE_URL`.
