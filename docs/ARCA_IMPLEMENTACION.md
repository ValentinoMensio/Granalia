# Plan de Implementacion ARCA

Este documento define el plan para integrar ARCA en Granalia de forma segura, manteniendo la convivencia entre comprobantes internos, facturacion declarada y pedidos divididos.

Nota operativa y legal: en la UI, PDFs y comunicaciones internas se debe evitar el texto "no declarada". Usar "comprobante interno", "pedido interno" o "interna". La convivencia entre comprobantes internos y facturacion fiscal debe validarse con contador/asesor fiscal antes de activar produccion.

## Objetivos

- Permitir emitir comprobantes internos como hasta ahora.
- Permitir generar Factura A declarada en estado borrador y autorizarla luego contra ARCA con un boton separado.
- Permitir cargar un pedido una sola vez y dividirlo en una parte interna y otra declarada.
- Mantener trazabilidad completa entre el pedido original y los comprobantes derivados.
- Bloquear edicion/eliminacion de comprobantes fiscales autorizados.
- Preparar la aplicacion para homologacion ARCA sin requerir certificado/key desde el primer paso.

## Datos Confirmados

- Granalia emite Factura A.
- Granalia es Responsable Inscripto.
- Condicion de venta: cuenta corriente.
- Hay productos con IVA 21%: procesados.
- Hay productos con IVA 10,5%: naturales.
- Los precios internos cargados actualmente son sin IVA y usan otra lista de precios.
- El flujo de ARCA debe convivir con comprobantes internos.
- La autorizacion ARCA debe hacerse con boton separado.
- No hay certificado/key de homologacion todavia.
- En modo dividido, el porcentaje declarado se aplica sobre cantidades.
- No se aceptan cantidades decimales porque todos los productos son packs.
- El porcentaje declarado es global y se aplica a cada producto.
- La factura declarada se guarda como draft, puede editarse, y luego se autoriza. Despues de autorizada ya no se puede editar.
- La division de cantidades usa redondeo hacia arriba para la parte declarada.
- Debe existir una contrasena para autorizar la creacion de facturas sensibles.

## Modos De Facturacion

### Solo Interna

- Genera un unico comprobante interno.
- No llama a ARCA.
- No usa CAE.
- Usa lista de precios interna.
- Es editable/eliminable segun las reglas actuales.
- Estado fiscal: `internal`.

### Solo Declarada

- Genera una unica Factura A fiscal en estado `draft`.
- No llama automaticamente a ARCA.
- Usa lista de precios declarada.
- Requiere datos fiscales del cliente.
- Se puede editar mientras este en `draft`, `rejected` o `error`.
- Se autoriza con boton separado `Autorizar en ARCA`.
- Una vez autorizada queda bloqueada.
- Estados posibles: `draft`, `authorized`, `rejected`, `error`.

### Dividida

- Carga un pedido completo una sola vez.
- Genera dos comprobantes vinculados:
  - Parte interna: comprobante interno.
  - Parte declarada: Factura A fiscal en `draft`.
- Usa dos listas de precio:
  - Lista interna.
  - Lista declarada.
- Aplica un porcentaje declarado global a cada producto.
- La parte declarada se puede autorizar luego contra ARCA.

## Regla De Division Por Cantidades

La cantidad declarada se calcula por linea usando redondeo hacia arriba:

```txt
cantidad_declarada = ceil(cantidad_total * porcentaje_declarado / 100)
cantidad_no_declarada = cantidad_total - cantidad_declarada
```

Ejemplos con 30% declarado:

| Cantidad total | Declarada | Interna |
| --- | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 10 | 3 | 7 |
| 11 | 4 | 7 |

Esta regla favorece la parte declarada cuando el calculo no da entero.

## Web Service ARCA A Usar

ARCA ofrece mas de un Web Service para factura electronica. La decision debe cerrarse antes de implementar homologacion real.

### Opcion Recomendada Inicial: WSFEv1

Usar `wsfev1` si Granalia solo necesita autorizar Factura A con importes agregados:

- Importe total.
- Neto gravado.
- IVA discriminado por alicuota.
- Documento del receptor.
- Punto de venta.
- Tipo de comprobante.
- CAE.

Con WSFEv1 no se envia el detalle de cada producto a ARCA. El detalle de items se mantiene en Granalia para PDF, auditoria interna y reconstruccion historica.

### Opcion A Evaluar: WSMTXCA

Evaluar `wsmtxca` si se requiere enviar detalle de items/productos a ARCA.

Decision pendiente: confirmar con contador/asesor fiscal si alcanza WSFEv1 para la operacion de Granalia. Para la primera version se recomienda disenar el dominio de forma compatible con WSFEv1 y conservar snapshots internos completos por linea.

## Modelo De Datos Propuesto

### Tabla Nueva: `invoice_batches`

Agrupa comprobantes generados desde un mismo pedido.

Campos sugeridos:

- `id`
- `customer_id`
- `client_name`
- `order_date`
- `billing_mode`: `internal_only`, `fiscal_only`, `split`
- `declared_percentage`
- `internal_percentage`
- `internal_price_list_id`
- `fiscal_price_list_id`
- `created_by_user_id`
- `created_at`

### Campos Nuevos En `invoices`

- `batch_id`: referencia a `invoice_batches.id`.
- `split_kind`: `internal` o `fiscal`.
- `split_percentage`.
- `fiscal_status`: `internal`, `draft`, `authorized`, `rejected`, `error`.
- `fiscal_locked_at`.
- `fiscal_authorized_at`.
- `arca_environment`: `homologacion` o `produccion`.
- `arca_cuit_emisor`.
- `arca_cbte_tipo`: Factura A.
- `arca_concepto`: productos.
- `arca_doc_tipo`: CUIT.
- `arca_doc_nro`.
- `arca_point_of_sale`.
- `arca_invoice_number`.
- `arca_cae`.
- `arca_cae_expires_at`.
- `arca_result`.
- `arca_observations`.
- `arca_error_code`.
- `arca_error_message`.
- `arca_request_id`.

### Breakdown Fiscal Agregado

Agregar columnas en `invoices` o una tabla dedicada `invoice_tax_breakdown`. Recomendacion: usar tabla dedicada si se quiere soportar nuevas alicuotas sin migraciones futuras.

Columnas directas sugeridas para primera version:

- `fiscal_net_21`.
- `fiscal_iva_21`.
- `fiscal_net_105`.
- `fiscal_iva_105`.
- `fiscal_net_total`.
- `fiscal_iva_total`.
- `fiscal_total`.

Tabla alternativa `invoice_tax_breakdown`:

- `id`.
- `invoice_id`.
- `iva_rate`.
- `arca_iva_id`.
- `base_amount`.
- `iva_amount`.
- `created_at`.

Este breakdown es obligatorio para construir el array `Iva` de WSFEv1 y auditar redondeos por alicuota.

### Campos Nuevos En `invoice_items`

Estos campos permiten reconstruir la factura fiscal historica aunque cambien productos, listas o alicuotas.

- `iva_rate`: `0.21` o `0.105`.
- `net_amount`.
- `iva_amount`.
- `fiscal_total`.

### Campos Fiscales En Catalogo

Agregar al producto o a la presentacion:

- `iva_rate`: `0.21` o `0.105`.
- Opcional: `tax_category`: `processed` o `natural`.

Recomendacion inicial: guardar el IVA a nivel producto si todas sus presentaciones comparten alicuota. Si puede cambiar por presentacion, guardarlo a nivel presentacion.

### Tabla Recomendada: `arca_requests`

Para auditoria profesional de comunicaciones con ARCA.

- `id`
- `invoice_id`
- `operation`: `FECompUltimoAutorizado`, `FECAESolicitar`, etc.
- `environment`
- `request_hash`
- `sanitized_request`
- `sanitized_response`
- `status`
- `error_code`
- `error_message`
- `created_at`

Recomendacion: usar esta tabla en vez de guardar payloads raw completos en `invoices`. Los request/response deben estar sanitizados, con retencion limitada o cifrados si se decide conservar datos sensibles. No guardar token/sign, private keys ni secretos.

## Estados Fiscales

- `internal`: comprobante interno, no fiscal.
- `draft`: comprobante fiscal preparado, editable, no autorizado.
- `authorized`: comprobante fiscal autorizado por ARCA, bloqueado.
- `rejected`: ARCA rechazo la solicitud; se puede corregir y reintentar.
- `error`: fallo tecnico o de comunicacion; se puede reintentar.

## Reglas De Seguridad Y Bloqueo

- Un comprobante `authorized` no se puede editar.
- Un comprobante `authorized` no se puede eliminar.
- Una correccion futura de comprobante autorizado debe hacerse con nota de credito/debito.
- La autorizacion ARCA debe ser idempotente y tener prioridad maxima: no puede autorizar dos veces el mismo comprobante.
- La creacion de comprobantes fiscales o divididos debe ser transaccional.
- En modo dividido, se crean ambos comprobantes o ninguno.
- No guardar claves privadas ni certificados en la base de datos.
- No loguear contrasenas, certificados, private keys, token/sign ni payloads sensibles completos sin sanitizar.
- Si una autorizacion tiene timeout o error despues de enviar a ARCA, antes de reintentar se debe consultar/conciliar el ultimo comprobante autorizado y el estado esperado para evitar duplicados.

## Numeracion Fiscal E Idempotencia

La numeracion fiscal declarada no debe depender de una secuencia local como fuente de verdad.

Reglas para `POST /api/invoices/{invoice_id}/arca/authorize`:

- Obtener lock transaccional sobre la factura fiscal.
- Verificar que `fiscal_status` no sea `authorized`.
- Consultar `FECompUltimoAutorizado` para el punto de venta y tipo de comprobante.
- Calcular el proximo numero como ultimo autorizado + 1.
- Registrar intento de autorizacion en `arca_requests` con hash/idempotency key.
- Enviar `FECAESolicitar`.
- Si ARCA autoriza, persistir CAE, vencimiento, numero oficial y estado `authorized` en la misma transaccion logica de cierre.
- Si ARCA rechaza, persistir `rejected` y observaciones.
- Si hay error tecnico o timeout, persistir `error` y exigir conciliacion/consulta antes de reintentar automaticamente.

No reservar numeros fiscales localmente salvo como dato temporal de intento. El numero oficial solo queda firme cuando ARCA autoriza o cuando se concilia una autorizacion ya aceptada por ARCA.

## Contrasena De Autorizacion

Debe existir una contrasena adicional para autorizar operaciones sensibles.

### Operaciones Que Deben Pedir Contrasena

Recomendacion inicial:

- Crear `Solo declarada`.
- Crear `Dividida`.
- Autorizar en ARCA.

Pendiente de confirmar:

- Si tambien debe pedirse para `Solo interna`.

### Implementacion Segura

- No guardar la contrasena en texto plano.
- Usar hash fuerte, preferentemente bcrypt.
- Configuracion sugerida: `GRANALIA_INVOICE_AUTH_PASSWORD_HASH`.
- El frontend pide la contrasena en modal y la envia solo en la request necesaria.
- El backend valida y descarta la contrasena inmediatamente.
- Respuesta de error generica: `Contrasena de autorizacion invalida`.

## Configuracion ARCA

Variables sugeridas:

- `GRANALIA_ARCA_ENABLED=false`
- `GRANALIA_ARCA_ENV=homologacion`
- `GRANALIA_ARCA_CUIT`
- `GRANALIA_ARCA_POINT_OF_SALE`
- `GRANALIA_ARCA_CERT_PATH`
- `GRANALIA_ARCA_KEY_PATH`
- `GRANALIA_ARCA_KEY_PASSWORD`
- `GRANALIA_ARCA_WSAA_URL`
- `GRANALIA_ARCA_WSFE_URL`
- `GRANALIA_ARCA_SERVICE=wsfev1`

Mientras `GRANALIA_ARCA_ENABLED=false`, el boton `Autorizar en ARCA` debe aparecer deshabilitado o devolver un error claro: `ARCA no configurado`.

Antes de homologar se debe validar que el punto de venta este habilitado para Web Services y CAE/CAEA para la CUIT emisora. ARCA permite consultar puntos de venta con `FEParamGetPtosVenta`.

## Modulos Backend Propuestos

```txt
backend/app/services/arca/
  __init__.py
  config.py
  models.py
  wsaa.py
  wsfe.py
  client.py
```

Responsabilidades:

- `config.py`: carga y valida configuracion ARCA.
- `models.py`: tipos internos normalizados.
- `wsaa.py`: autenticacion, TRA, CMS, token/sign.
- `wsfe.py`: operaciones WSFEv1.
- `wsmtxca.py`: placeholder futuro si se confirma necesidad de detalle de items ante ARCA.
- `client.py`: interfaz de alto nivel usada por rutas/servicios de facturacion.

## Endpoints Propuestos

### Generar Comprobantes

`POST /api/invoices`

Extender payload actual con:

- `billing_mode`: `internal_only`, `fiscal_only`, `split`.
- `declared_percentage`.
- `internal_price_list_id`.
- `fiscal_price_list_id`.
- `authorization.password`, para modos sensibles.

Respuesta sugerida:

```json
{
  "batch_id": 123,
  "invoices": [
    { "invoice_id": 170, "split_kind": "internal", "fiscal_status": "internal" },
    { "invoice_id": 171, "split_kind": "fiscal", "fiscal_status": "draft" }
  ]
}
```

### Autorizar En ARCA

`POST /api/invoices/{invoice_id}/arca/authorize`

Reglas:

- Solo admin.
- Requiere contrasena de autorizacion.
- Solo comprobantes `split_kind=fiscal`.
- Solo estados `draft`, `rejected` o `error`.
- Si ya esta `authorized`, no reintentar.
- Valida datos fiscales antes de llamar a ARCA.
- Consulta `FECompUltimoAutorizado` antes de solicitar CAE.
- Construye importes agregados y array `Iva` desde `invoice_tax_breakdown`.

### Consultar Estado ARCA

Opcional:

`GET /api/invoices/{invoice_id}/arca/status`

## Validaciones Antes De Generar Fiscal

- Cliente con CUIT valido.
- Razon social o nombre fiscal.
- Condicion IVA del cliente si se agrega en el modelo.
- Lista declarada seleccionada.
- Todos los productos con IVA configurado.
- Todas las lineas tienen cantidad entera mayor a cero.
- No hay productos/formats faltantes en la lista declarada.
- Comprobante no esta autorizado.

## Calculo Fiscal

Factura A debe discriminar IVA.

Para cada linea declarada:

```txt
net_amount = precio_neto * cantidad
iva_amount = net_amount * iva_rate
fiscal_total = net_amount + iva_amount
```

Importante: queda pendiente confirmar si la lista declarada usa precios netos sin IVA o precios finales con IVA incluido. Hasta confirmar, no cerrar la implementacion del calculo ARCA real.

### Redondeo Fiscal

Debe existir una politica explicita de redondeo fiscal a 2 decimales.

Recomendacion inicial:

- Calcular neto por linea con precision decimal.
- Redondear neto de linea a 2 decimales.
- Calcular IVA de linea sobre neto redondeado.
- Redondear IVA de linea a 2 decimales.
- Agrupar por alicuota para obtener `BaseImp` e `Importe` del array `Iva`.
- Calcular totales fiscales desde el breakdown agrupado, no recalcularlos de forma independiente.
- Guardar diferencias/ajustes de redondeo si aparecen.

Esta politica debe validarse en homologacion con facturas de una alicuota, dos alicuotas y cantidades variadas.

## UX Propuesta

### Creador De Facturas

Agregar seccion `Modo de facturacion`:

- `Solo interna`.
- `Solo declarada`.
- `Dividida`.

Campos segun modo:

- Interna:
  - Lista interna.
- Declarada:
  - Lista declarada.
- Dividida:
  - Lista interna.
  - Lista declarada.
  - `% declarado`.
  - `% interno` calculado.

Preview en modo dividido:

- Cantidades internas por linea.
- Cantidades declaradas por linea.
- Total interno estimado.
- Total declarado estimado.
- Advertencias por faltantes de catalogo o IVA.

### Historial

- Mostrar comprobantes vinculados por `batch_id`.
- Mostrar modo:
  - `Interna`.
  - `Factura A draft`.
  - `Factura A autorizada`.
  - `Factura A rechazada`.
- Boton `Autorizar en ARCA` solo para fiscales no autorizadas.

### Detalle/PDF

Interna:

- Mostrar como comprobante interno.
- No mostrar CAE.

Nota de naming: evitar mostrar "no declarada". Usar "Interna" o "Comprobante interno".

Declarada draft:

- Mostrar como precomprobante fiscal sin CAE.
- Indicar que todavia no esta autorizado.

Declarada autorizada:

- Mostrar CAE.
- Mostrar vencimiento CAE.
- Mostrar punto de venta.
- Mostrar numero oficial.
- Mostrar condicion de venta: cuenta corriente.
- Mostrar IVA discriminado.

## Paso A Paso De Implementacion

### Fase 1: Base Fiscal Sin ARCA Real

1. Crear migracion para `invoice_batches`.
2. Crear migracion para campos fiscales en `invoices`.
3. Crear migracion para `invoice_tax_breakdown` o columnas agregadas por alicuota en `invoices`.
4. Crear migracion para campos IVA snapshot en `invoice_items`.
5. Agregar campos de IVA en catalogo/productos/ofertas.
6. Actualizar schemas Pydantic.
7. Actualizar bootstrap y endpoints para exponer IVA y estado fiscal.
8. Agregar validacion de contrasena de autorizacion en backend.
9. Reemplazar naming visible sensible por "interna".

### Fase 2: UI De Modos Y Split

1. Agregar selector `Modo de facturacion` en el creador.
2. Agregar seleccion de lista interna y lista declarada.
3. Agregar `% declarado` para modo dividido.
4. Implementar preview de split por cantidades enteras con `ceil`.
5. Mostrar advertencias si faltan productos/formats en alguna lista.
6. Agregar modal de contrasena para modos sensibles.

### Fase 3: Generacion Transaccional

1. Refactorizar `POST /api/invoices` para soportar `billing_mode`.
2. Implementar `internal_only`.
3. Implementar `fiscal_only` como draft.
4. Implementar `split` generando batch + 2 invoices.
5. Guardar snapshots fiscales por linea.
6. Asegurar que split cree todos los comprobantes o ninguno.
7. Ajustar historial y detalle para mostrar batches.

### Fase 4: Reglas De Bloqueo

1. Bloquear edicion de `authorized`.
2. Bloquear eliminacion de `authorized`.
3. Permitir edicion de fiscal `draft`, `rejected`, `error`.
4. En batch split, si se editan cantidades o lineas mientras nada esta autorizado, regenerar el split completo.
5. En batch split con parte fiscal autorizada, bloquear edicion del batch completo salvo futuras notas de credito/debito y ajustes internos controlados.

### Fase 5: Preparacion ARCA

1. Crear estructura `services/arca`.
2. Agregar config ARCA.
3. Agregar endpoint `POST /api/invoices/{id}/arca/authorize`.
4. Si ARCA no esta configurado, devolver error claro.
5. Agregar auditoria de intentos de autorizacion.
6. Agregar UI del boton `Autorizar en ARCA`.
7. Implementar log sanitizado en `arca_requests`.
8. Implementar construccion de breakdown por alicuota y array `Iva`.
9. Implementar politica de redondeo fiscal.

### Fase 6: Homologacion ARCA

1. Obtener certificado/key de homologacion.
2. Configurar WSAA homologacion.
3. Implementar token/sign.
4. Validar punto de venta con `FEParamGetPtosVenta`.
5. Implementar `FECompUltimoAutorizado`.
6. Implementar `FECAESolicitar`.
7. Probar Factura A con IVA 21%.
8. Probar Factura A con IVA 10,5%.
9. Probar factura mixta con ambas alicuotas.
10. Probar rechazo por CUIT invalido.
11. Probar timeout/error tecnico y conciliacion antes de reintento.

### Fase 7: Produccion

1. Obtener certificado/key productivo.
2. Confirmar punto de venta habilitado para Web Services.
3. Configurar variables productivas.
4. Hacer prueba controlada.
5. Activar boton ARCA productivo.

## Preguntas Pendientes

1. Usar WSFEv1 o WSMTXCA? Si no se requiere detalle de items ante ARCA, WSFEv1 alcanza; si ARCA debe recibir detalle de productos, evaluar WSMTXCA.
2. La lista declarada, cuando exista, tiene precios netos sin IVA o precios finales con IVA incluido?
3. El IVA se define por producto o por presentacion?
4. La contrasena de autorizacion debe pedirse tambien para `Solo interna`?
5. Quien administra/cambia la contrasena de autorizacion: variable de entorno o UI de administracion?
6. En modo dividido, si una linea tiene cantidad 1 y porcentaje declarado bajo, esta confirmado que queda 1 declarado y 0 interno por redondeo hacia arriba?
7. Si una factura split tiene parte fiscal autorizada, se bloquea la edicion de todo el batch o solo de la factura fiscal? Recomendacion: bloquear todo el batch.
8. Se necesitaran notas de credito/debito en la primera version o se dejan para una segunda etapa?
9. Los clientes tienen condicion IVA registrada o hay que agregarla?
10. El punto de venta ARCA ya existe o debe crearse/habilitarse?
11. Se quiere agrupar visualmente el historial por pedido/batch o mostrar cada comprobante como fila independiente con referencia al batch?
12. Las facturas internas deben seguir usando la misma numeracion visible actual o una secuencia separada `Interna`?
13. El PDF de factura declarada draft debe imprimirse o solo previsualizarse como borrador?
14. Cual sera la politica final de retencion de logs ARCA sanitizados?

## Riesgos Y Mitigaciones

- Doble autorizacion ARCA: usar bloqueo transaccional e idempotencia por invoice.
- Timeout posterior a autorizacion real: conciliar contra ARCA antes de cualquier reintento.
- Error de IVA por datos incompletos: bloquear autorizacion si falta `iva_rate`.
- Descuadre de centavos: usar politica explicita de redondeo y breakdown por alicuota.
- Confusion entre interna y fiscal: UI/PDF deben etiquetar claramente cada tipo.
- Edicion indebida de autorizadas: reglas backend obligatorias, no solo UI.
- Edicion de split fiscal draft: si cambian lineas/cantidades, regenerar ambas partes mientras nada este autorizado.
- Certificados expuestos: usar archivos fuera del repo y variables seguras.
- Split con cantidades pequenas: preview obligatorio antes de generar.
- Rechazos ARCA: guardar observaciones y permitir correccion mientras no este autorizado.

## Recomendacion De Implementacion Inicial

Implementar primero todo lo necesario para operar los tres modos y dejar facturas fiscales en `draft`, sin conectar ARCA real. Esto permite validar datos, split, UI, estados, bloqueos y previews. Luego, cuando este disponible el certificado/key de homologacion, conectar WSAA/WSFE y probar autorizacion real.
