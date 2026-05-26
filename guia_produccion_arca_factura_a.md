# Guía de producción ARCA para Factura A — Granalia

> Objetivo: dejar documentado cómo debe configurarse y operarse Granalia para emitir Factura A en producción usando ARCA, siguiendo el criterio de las guías oficiales y el diseño implementado en el proyecto.

## 1. Alcance

Esta guía cubre:

- Certificado digital productivo.
- Delegación de Web Services en ARCA.
- Configuración `.env` para producción.
- Consulta de datos fiscales del cliente.
- Factura A por WSFEv1.
- Condición IVA receptor.
- Idempotencia y recuperación de autorización.
- PDF y QR fiscal.
- Checklist antes de emitir comprobantes reales.

No cubre liquidaciones contables, registración impositiva posterior ni presentación de declaraciones juradas.

## 2. Servicios ARCA que hay que habilitar

Para Granalia se deben habilitar, como mínimo, estos servicios al certificado productivo usado por el backend.

### 2.1 Facturación Electrónica / WSFEv1

Servicio requerido para emitir comprobantes electrónicos A, B, C y M por Web Service y obtener CAE/CAEA.

Buscar en ARCA con nombres similares a:

- `Facturación Electrónica`
- `WebService de Facturación Electrónica`
- `WSFE`
- `wsfev1`

Granalia lo usa para:

- `FECompUltimoAutorizado`
- `FECAESolicitar`
- `FECompConsultar`
- `FEParamGetCondicionIvaReceptor`

Referencia oficial: ARCA/AFIP documenta `wsfev1 - R.G. N° 4.291` como el servicio para Factura Electrónica y publica el manual de desarrollador v4.2 para WSFEv1.

Fuentes:

- https://www.afip.gob.ar/ws/documentacion/ws-factura-electronica.asp
- https://www.arca.gob.ar/ws/documentacion/manuales/manual-desarrollador-ARCA-COMPG-v4-1.pdf

### 2.2 Consulta de Constancia de Inscripción / Padrón

Servicio requerido para buscar datos fiscales de clientes por CUIT.

Buscar en ARCA con nombres similares a:

- `Servicio Consulta Constancia de Inscripción`
- `Consulta de Constancia de Inscripción`
- `Constancia de Inscripción`
- `Padrón`

El service id técnico es:

```text
ws_sr_constancia_inscripcion
```

Granalia lo usa cuando está configurado:

```env
GRANALIA_ARCA_PADRON_SERVICE=ws_sr_constancia_inscripcion
```

Según el manual oficial, ese id de servicio es el que se debe usar al solicitar el Ticket de Acceso WSAA.

Fuentes:

- https://www.afip.gob.ar/ws/WSCI/manual-ws-sr-ws-constancia-inscripcion-v3.4.pdf
- https://www.afip.gob.ar/ws/WSCI/manual_ws_sr_ws_constancia_inscripcion.pdf

### 2.3 Padrón Alcance 13, opcional recomendado

Servicio recomendado como fallback para obtener datos públicos básicos, identificación y domicilios cuando la constancia de inscripción no alcanza.

Buscar en ARCA con nombres similares a:

- `Padrón Alcance 13`
- `Consulta a Padrón Alcance 13`
- `ws_sr_padron_a13`

Fuente:

- https://www.arca.gob.ar/ws/ws-padron-a13/manual-ws-sr-padron-a13-v1.3.pdf

## 3. Ruta para delegar servicios en ARCA

Entrar con clave fiscal de la CUIT emisora.

Ruta general:

```text
Administrador de Relaciones de Clave Fiscal
→ Nueva relación / Adherir servicio
→ ARCA / AFIP
→ WebServices
→ seleccionar servicio
→ seleccionar representante / computador fiscal / alias
→ elegir alias del certificado productivo
→ confirmar
```

Para este proyecto, el alias actual recomendado es:

```text
granalia-prod-2026
```

Repetir el proceso para:

```text
Facturación Electrónica / WSFEv1
Servicio Consulta Constancia de Inscripción
Padrón Alcance 13, si se decide usar fallback
```

## 4. Certificado digital productivo

El certificado productivo debe ser distinto del certificado de homologación.

Archivos actuales correctos en el servidor:

```text
/app/certs/granalia-prod-2026.crt
/app/certs/granalia-prod-2026.key
```

Se verificó que certificado y clave matchean porque ambos dieron el mismo módulo MD5:

```text
37881da19924f163602bcb1578e79a4e
```

Comandos de verificación:

```bash
openssl x509 -noout -modulus \
  -in ~/arca-produccion/granalia-prod-2026.crt | openssl md5

openssl rsa -noout -modulus \
  -in ~/arca-produccion/granalia-produccion.key | openssl md5
```

La clave privada nunca debe subirse a ARCA ni compartirse. ARCA recibe el CSR y devuelve el certificado `.crt`.

## 5. Configuración recomendada para probar padrón en producción

Para probar búsqueda de datos fiscales reales sin emitir facturas reales, usar producción con `DRY_RUN=true`.

```env
GRANALIA_ARCA_ENABLED=true
GRANALIA_ARCA_ENV=production
GRANALIA_ARCA_CUIT=20225790346
GRANALIA_ARCA_POINT_OF_SALE=<PUNTO_DE_VENTA_PRODUCTIVO>
GRANALIA_ARCA_CERT_PATH=/app/certs/granalia-prod-2026.crt
GRANALIA_ARCA_KEY_PATH=/app/certs/granalia-prod-2026.key
GRANALIA_ARCA_KEY_PASSWORD=
GRANALIA_ARCA_DRY_RUN=true
GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER=false
GRANALIA_ARCA_TIMEOUT_SECONDS=30
GRANALIA_ARCA_TOKEN_CACHE_PATH=/tmp/granalia-arca-wsaa-token-prod.json
GRANALIA_ARCA_RECEIVER_IVA_CONDITION_ID=1
GRANALIA_ARCA_PADRON_SERVICE=ws_sr_constancia_inscripcion
```

Importante:

- `GRANALIA_ARCA_DRY_RUN=true` debe mantenerse mientras se prueba padrón/configuración.
- No poner `DRY_RUN=false` en producción hasta estar listo para emitir comprobantes reales.
- En producción, una llamada exitosa a `FECAESolicitar` puede generar un comprobante fiscal real con CAE y numeración real.

## 6. Configuración para producción real de Factura A

Cuando ya esté todo probado y se decida emitir comprobantes reales:

```env
GRANALIA_ARCA_ENABLED=true
GRANALIA_ARCA_ENV=production
GRANALIA_ARCA_CUIT=20225790346
GRANALIA_ARCA_POINT_OF_SALE=<PUNTO_DE_VENTA_PRODUCTIVO>
GRANALIA_ARCA_CERT_PATH=/app/certs/granalia-prod-2026.crt
GRANALIA_ARCA_KEY_PATH=/app/certs/granalia-prod-2026.key
GRANALIA_ARCA_KEY_PASSWORD=
GRANALIA_ARCA_DRY_RUN=false
GRANALIA_ARCA_MARK_AUTHORIZED=true
GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER=false
GRANALIA_ARCA_TIMEOUT_SECONDS=30
GRANALIA_ARCA_TOKEN_CACHE_PATH=/tmp/granalia-arca-wsaa-token-prod.json
GRANALIA_ARCA_PADRON_SERVICE=ws_sr_constancia_inscripcion
```

`GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER=false` es obligatorio como política productiva: en producción no se deben emitir Facturas A basadas únicamente en datos fiscales manuales sin validación o snapshot vigente.

## 7. Flujo correcto para buscar datos fiscales del cliente

Granalia debe buscar los datos fiscales desde el backend, no desde el frontend directo.

Flujo:

```text
Frontend CustomerEditor
→ GET /api/customers/taxpayer/{cuit}
→ backend/app/api/routes/customers.py
→ lookup_taxpayer_data(cuit)
→ backend/app/services/arca/padron.py
→ ws_sr_constancia_inscripcion / getPersona_v2
```

Request conceptual al padrón:

```xml
<cuitRepresentada>CUIT_EMISOR</cuitRepresentada>
<idPersona>CUIT_CONSULTADO</idPersona>
```

La CUIT representada debe ser la CUIT emisora configurada en:

```env
GRANALIA_ARCA_CUIT=20225790346
```

Si ARCA responde que no existe persona con ese ID en homologación, no necesariamente es error de código. En homologación los padrones no siempre tienen todas las CUIT reales. Para validar datos reales, suele ser necesario probar contra producción.

## 8. Datos mínimos para Factura A

Antes de crear o autorizar una Factura A, el backend debe exigir:

- CUIT receptor válido de 11 dígitos.
- Tipo de documento receptor `80` para CUIT.
- Razón social / nombre fiscal.
- Domicilio fiscal o comercial fiscalmente utilizable.
- Condición IVA receptor.
- `CondicionIVAReceptorId` resuelto desde catálogo ARCA.
- Ítems con alícuota IVA explícita.
- Neto gravado, IVA y total calculados server-side.
- Punto de venta productivo habilitado.
- Tipo de comprobante correcto: Factura A = `1`.
- Moneda y cotización.

La Factura A productiva no debe depender del cliente vivo al momento de renderizar o consultar después; debe usar snapshot fiscal congelado.

## 9. Condición IVA receptor según WSFEv1 2026

El manual WSFEv1 v4.2 incorpora `CondicionIVAReceptorId` dentro de los datos enviados a `FECAESolicitar` y el método:

```text
FEParamGetCondicionIvaReceptor
```

Granalia debe:

1. Consultar `FEParamGetCondicionIvaReceptor`.
2. Cachear resultados en `arca_iva_conditions`.
3. Resolver server-side el ID desde `customer_iva_condition`.
4. Enviar `CondicionIVAReceptorId` en `FECAESolicitar`.
5. Bloquear autorización si no hay mapeo válido.

El frontend no debe decidir el ID fiscal enviado a ARCA. Solo debe mostrar o permitir editar la condición fiscal textual del cliente.

Fuente:

- https://www.arca.gob.ar/ws/documentacion/manuales/manual-desarrollador-ARCA-COMPG-v4-1.pdf

## 10. Snapshot fiscal del receptor

Al crear o editar un draft fiscal, Granalia debe generar y guardar:

```json
{
  "doc_tipo": 80,
  "doc_nro": "30700000000",
  "fiscal_name": "CLIENTE SA",
  "iva_condition": "RESPONSABLE_INSCRIPTO",
  "condicion_iva_receptor_id": 1,
  "fiscal_address": "DOMICILIO FISCAL",
  "padron_checked_at": "2026-05-25T12:00:00Z",
  "source": "arca_padron"
}
```

Ese snapshot debe ser la fuente para:

- autorización ARCA;
- PDF fiscal;
- QR fiscal;
- auditoría futura.

Regla productiva recomendada:

```text
Factura A productiva = requiere snapshot fiscal receptor vigente.
```

Vigencia inicial recomendada:

```text
7 días
```

Si el snapshot no existe o está vencido, producción debe intentar consultar padrón. Si no puede validar, debe bloquear la autorización salvo una política administrativa explícita.

## 11. Idempotencia y recuperación ARCA

Regla central del sistema:

```text
Nunca llamar de nuevo a FECAESolicitar si ya existe un intento con número asignado sin antes consultar FECompConsultar.
```

Flujo correcto:

1. Validar factura localmente.
2. Si ya tiene `arca_cae` y `arca_invoice_number`, devolver resultado existente.
3. Si tiene `arca_request_id` vigente con número asignado, primero ejecutar recuperación con `FECompConsultar`.
4. Si no hay intento vigente:
   - llamar `FECompUltimoAutorizado`;
   - calcular próximo número;
   - crear `arca_requests` en estado `pending`;
   - reservar `environment + issuer_cuit + point_of_sale + cbte_tipo + cbte_number`;
   - guardar `arca_request_id` en la factura;
   - marcar factura como `authorizing`.
5. Llamar `FECAESolicitar`.
6. Si autoriza:
   - guardar CAE;
   - guardar vencimiento CAE;
   - guardar número fiscal;
   - marcar `authorized` en producción o `authorized_homologation` en homologación.
7. Si rechaza funcionalmente:
   - marcar `rejected`;
   - conservar respuesta ARCA.
8. Si hay timeout o error técnico ambiguo después de asignar número:
   - llamar `FECompConsultar`;
   - si encuentra CAE, sincronizar;
   - si no encuentra, marcar `authorization_failed`.

## 12. Estados fiscales

Estados permitidos:

```text
draft
authorizing
authorized
authorized_homologation
authorization_failed
rejected
error
internal
```

Regla de bloqueo:

```text
Solo bloquea definitivamente si:
fiscal_status == "authorized"
y arca_environment == "production" o "produccion"
```

`authorized_homologation` no bloquea fiscalmente.

## 13. PDF y QR fiscal

El QR fiscal debe generarse solo si existe autorización real con CAE/CAEA.

La especificación oficial del QR indica que el QR codifica, entre otros datos:

- fecha de emisión;
- CUIT emisor;
- punto de venta;
- tipo de comprobante;
- número de comprobante;
- importe total;
- moneda;
- cotización;
- tipo y número de documento receptor;
- tipo de autorización;
- código de autorización.

Fuente:

- https://www.afip.gob.ar/fe/qr/
- https://www.afip.gob.ar/fe/qr/documentos/QRespecificaciones.pdf

### 13.1 PDF draft fiscal

Permitido sin CAE, pero debe mostrar watermark:

```text
BORRADOR - NO VALIDO COMO COMPROBANTE FISCAL
```

No debe mostrar QR fiscal final ni CAE falso.

### 13.2 PDF fiscal autorizado

Debe generarse solo desde datos persistidos/autorizados:

- `customer_fiscal_snapshot`
- `invoice.items_fiscal_snapshot`
- `invoice_tax_breakdown`
- `arca_cae`
- `arca_cae_due_date`
- `arca_invoice_number`
- `arca_cbte_tipo`
- `arca_point_of_sale`
- `arca_environment`
- total fiscal autorizado

No debe usar defaults de `.env`, cliente vivo ni productos actuales para reconstruir una factura ya autorizada.

## 14. Checklist operativo antes de pasar a producción real

### ARCA

- [ ] Certificado productivo creado desde CSR correcto.
- [ ] `.crt` y `.key` verificados con el mismo módulo.
- [ ] Alias `granalia-prod-2026` vigente.
- [ ] Web Service Facturación Electrónica / WSFEv1 delegado al alias.
- [ ] Servicio Consulta Constancia de Inscripción delegado al alias.
- [ ] Padrón Alcance 13 delegado si se usa fallback.
- [ ] Punto de venta productivo dado de alta y habilitado.
- [ ] CUIT emisora con Domicilio Fiscal Electrónico constituido.

### Backend

- [ ] Migraciones Alembic corridas en base real.
- [ ] `arca_requests` sin duplicados por número reservado.
- [ ] `invoices.arca_request_id` apunta al intento vigente.
- [ ] `GRANALIA_ARCA_ENV=production`.
- [ ] `GRANALIA_ARCA_DRY_RUN=true` para prueba inicial de padrón.
- [ ] `GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER=false`.
- [ ] Token cache productivo separado del de homologación.
- [ ] Logs y auditoría funcionando.

### Prueba segura inicial

Con producción y `DRY_RUN=true`:

- [ ] Probar `GET /api/customers/taxpayer/{cuit}`.
- [ ] Confirmar que trae razón social, domicilio y condición fiscal.
- [ ] Confirmar que se genera snapshot fiscal.
- [ ] Confirmar que no se emite CAE real.

### Primera emisión real controlada

Solo cuando se decida emitir de verdad:

- [ ] Cambiar `GRANALIA_ARCA_DRY_RUN=false`.
- [ ] Crear Factura A controlada.
- [ ] Autorizar y obtener CAE.
- [ ] Verificar comprobante con `FECompConsultar`.
- [ ] Verificar PDF.
- [ ] Escanear QR.
- [ ] Intentar editar y confirmar bloqueo.
- [ ] Revisar `arca_requests` y logs.

## 15. Comandos útiles

Ver variables reales dentro del contenedor:

```bash
docker exec deploy-api-1 env | grep GRANALIA_ARCA | sort
```

Ver certificados dentro del contenedor:

```bash
docker exec deploy-api-1 ls -la /app/certs
```

Reiniciar backend:

```bash
docker restart deploy-api-1
```

Verificar certificado y key:

```bash
openssl x509 -noout -modulus \
  -in ~/arca-produccion/granalia-prod-2026.crt | openssl md5

openssl rsa -noout -modulus \
  -in ~/arca-produccion/granalia-produccion.key | openssl md5
```

## 16. Riesgos principales

No pasar a producción real si ocurre alguno de estos puntos:

- El padrón productivo no valida la CUIT emisora o clientes.
- No está delegado WSFEv1 al alias productivo.
- No está delegado `ws_sr_constancia_inscripcion` al alias productivo.
- `DRY_RUN=false` está activo sin intención de emitir.
- El punto de venta no corresponde al ambiente productivo.
- Falta idempotencia o recuperación por `FECompConsultar`.
- El PDF/QR se genera con datos no autorizados.
- Se permite carga manual de cliente fiscal en producción.

## 17. Resumen final

Para producción, Granalia debe funcionar así:

```text
Cliente fiscal → validación padrón / snapshot vigente
Factura A draft → validación server-side + IVA + CondicionIVAReceptorId
Autorización → WSFEv1 con idempotencia + recuperación
Resultado → CAE + número + vencimiento + estado authorized
PDF/QR → solo desde datos autorizados y snapshot congelado
Bloqueo → factura productiva authorized queda inmutable
```

La búsqueda de datos fiscales para Factura A debe apoyarse principalmente en `ws_sr_constancia_inscripcion`. Para producción real, ese servicio tiene que estar delegado al alias `granalia-prod-2026`, junto con WSFEv1.
