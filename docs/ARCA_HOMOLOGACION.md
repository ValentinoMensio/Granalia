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
GRANALIA_ARCA_DRY_RUN=true
GRANALIA_ARCA_MARK_AUTHORIZED=false
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

## Modo seguro sin generar comprobantes

Con `GRANALIA_ARCA_DRY_RUN=true`, la accion `Autorizar en ARCA` valida WSAA, punto de venta y ultimo comprobante autorizado, pero no llama `autorizarComprobante` y no genera CAE.

Para habilitar emision real en homologacion, cambiar explicitamente:

```bash
GRANALIA_ARCA_DRY_RUN=false
GRANALIA_ARCA_MARK_AUTHORIZED=false
```

Con `GRANALIA_ARCA_ENV=homologacion` y `GRANALIA_ARCA_MARK_AUTHORIZED=false`, el backend llama `autorizarComprobante` y guarda CAE/numeracion de homologacion, pero conserva la factura sin bloquear y no la marca como `authorized`.

Para marcar facturas como autorizadas fiscalmente, usar produccion o configurar explicitamente:

```bash
GRANALIA_ARCA_MARK_AUTHORIZED=true
```

## Pruebas de CAE

Crear facturas fiscales desde la UI y usar `Autorizar en ARCA` en Historial. Si `GRANALIA_ARCA_DRY_RUN=true`, solo se valida conexion y numeracion tentativa sin generar comprobante.

Casos minimos:

- Factura A con IVA 21%.
- Factura A con IVA 10,5%.
- Factura A mixta con ambas alicuotas.
- Rechazo por CUIT invalido.
- Timeout/error tecnico: el backend consulta `consultarUltimoComprobanteAutorizado` y, si el numero quedo autorizado, intenta recuperar con `consultarComprobante` antes de permitir reintento.

## Servicio

Los metodos usados por defecto son de `wsmtxca`: `consultarPuntosVenta`, `consultarUltimoComprobanteAutorizado`, `consultarComprobante` y `autorizarComprobante`.
El parametro `GRANALIA_ARCA_WSFE_URL` sigue soportado por compatibilidad, pero para WSMTXCA se recomienda `GRANALIA_ARCA_SERVICE_URL`.
