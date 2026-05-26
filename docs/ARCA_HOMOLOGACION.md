# ARCA Homologacion

## Variables requeridas

```bash
GRANALIA_ARCA_ENABLED=true
GRANALIA_ARCA_ENV=homologacion
GRANALIA_ARCA_CUIT=20225790346
GRANALIA_ARCA_POINT_OF_SALE=<punto_de_venta_wsfev1>
GRANALIA_ARCA_PADRON_SERVICE=ws_sr_constancia_inscripcion
GRANALIA_ARCA_PADRON_OPERATION=getPersona_v2
GRANALIA_ARCA_PADRON_WSDL_URL=https://awshomo.arca.gob.ar/sr-padron/webservices/personaServiceA5?WSDL
GRANALIA_ARCA_PADRON_URL=https://awshomo.arca.gob.ar/sr-padron/webservices/personaServiceA5
GRANALIA_ARCA_CERT_PATH=/ruta/al/certificado.crt
GRANALIA_ARCA_KEY_PATH=/ruta/a/la/private.key
GRANALIA_ARCA_KEY_PASSWORD=<si_aplica>
GRANALIA_ARCA_DRY_RUN=true
GRANALIA_ARCA_MARK_AUTHORIZED=false
GRANALIA_INVOICE_AUTH_PASSWORD_HASH=<hash_scrypt>
```

URLs por defecto en homologacion:

```bash
GRANALIA_ARCA_WSAA_URL=https://wsaahomo.afip.gov.ar/ws/services/LoginCms
GRANALIA_ARCA_WSFE_URL=https://wswhomo.afip.gov.ar/wsfev1/service.asmx
GRANALIA_ARCA_PADRON_WSDL_URL=https://awshomo.arca.gob.ar/sr-padron/webservices/personaServiceA5?WSDL
GRANALIA_ARCA_PADRON_URL=https://awshomo.arca.gob.ar/sr-padron/webservices/personaServiceA5
```

## Diagnostico WSAA/WSFEv1

Desde la raiz del repo:

```bash
PYTHONPATH=backend python3 backend/scripts/arca_homologacion.py
```

Debe validar:

- WSAA `loginCms` con token/sign.
- `FEParamGetPtosVenta` contiene `GRANALIA_ARCA_POINT_OF_SALE`.
- `FECompUltimoAutorizado` responde para Factura A (`CbteTipo=1`).
- WSAA de padron pide token/sign con service `ws_sr_constancia_inscripcion`.
- Si se define `GRANALIA_ARCA_TEST_CUIT`, padron responde con `getPersona_v2` para esa CUIT.

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

El sistema usa WSFEv1 para facturacion: `FEParamGetPtosVenta`, `FECompUltimoAutorizado`, `FECompConsultar` y `FECAESolicitar`.
Usar `GRANALIA_ARCA_WSFE_URL` para sobrescribir el endpoint de facturacion. No configurar endpoints WSMTXCA en este sistema.

Para precargar datos fiscales del receptor, el backend usa por defecto `ws_sr_constancia_inscripcion` con el endpoint `personaServiceA5` y la operacion `getPersona_v2`.
Ese servicio reemplaza a los viejos `ws_sr_padron_*` para la consulta de constancia de inscripcion.

## Hash de autorizacion

`GRANALIA_INVOICE_AUTH_PASSWORD_HASH` debe usar el formato interno `scrypt$...` generado por `AuthManager.hash_password`. No se soportan hashes bcrypt en esta etapa.
