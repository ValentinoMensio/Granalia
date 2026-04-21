# Granalia Platform

Refactor completo con este stack:

- API: FastAPI
- Web: React + Vite + Tailwind
- Base de datos: PostgreSQL

La app ahora guarda todo en la base de datos:

- clientes
- transportes
- descuentos
- productos y presentaciones
- listas de precios PDF
- facturas
- lineas de factura
- archivos XLSX generados

## Esquema principal

Tablas operativas:

- `customers`
- `transports`
- `discount_policies`
- `products`
- `product_offerings`
- `price_lists`
- `invoices`
- `invoice_items`
- `catalogs`

Relaciones clave:

- cada `customer` puede tener un `transport` y una `discount_policy` por defecto
- cada `product` tiene muchas `product_offerings`
- cada `invoice` pertenece a un `customer`
- cada `invoice_item` pertenece a una `invoice` y referencia `product` + `product_offering`
- cada lista PDF queda almacenada en `price_lists`

## Levantar PostgreSQL

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Adminer:

- `http://127.0.0.1:8082/`

Credenciales por defecto:

- servidor: `postgres`
- usuario: `granalia`
- clave: `granalia`
- base: `granalia`

## Correr la API

```bash
cd backend
python3 -m alembic -c alembic.ini upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

API por defecto:

- `http://127.0.0.1:8000`
- docs: `http://127.0.0.1:8000/docs`

## Correr la web

```bash
cd frontend
npm install
npm run dev
```

Web por defecto:

- `http://127.0.0.1:5173`

Si querés apuntar la web a otra URL de API:

```bash
VITE_API_URL=http://127.0.0.1:8000 npm run dev
```

## HTTPS obligatorio con Caddy

La configuración segura queda en `deploy/Caddyfile` y `deploy/docker-compose.caddy.yml`.

Pasos recomendados:

1. construir el frontend estático

```bash
cd frontend
npm install
npm run build
```

2. levantar la API local en `127.0.0.1:8000`

```bash
cd backend
python3 -m alembic -c alembic.ini upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. levantar Caddy delante de la app

```bash
cd deploy
docker compose -f docker-compose.caddy.yml up -d
```

Acceso HTTPS:

- `https://granalia.localhost`

Notas de seguridad:

- la cookie de sesión se emite con `Secure` por defecto
- Caddy redirige tráfico y sirve la web por HTTPS
- `/api/*` se proxya a FastAPI con `X-Forwarded-Proto: https`
- se agregan headers de endurecimiento básicos (`HSTS`, `nosniff`, `X-Frame-Options`, etc.)

Para desarrollo local sin Caddy, podés desactivar temporalmente cookies seguras:

```bash
export GRANALIA_SECURE_COOKIES=false
```

No se recomienda en producción.

## Produccion recomendada

1. copiar variables base:

```bash
cp .env.example .env
```

2. completar secretos reales:

- `GRANALIA_SESSION_SECRET` con 32+ caracteres
- `POSTGRES_PASSWORD` fuerte
- `GRANALIA_POSTGRES_URL` apuntando al contenedor `postgres`
- `GRANALIA_ALLOWED_ORIGINS` con tu dominio real
- opcionalmente `GRANALIA_AUTH_PASSWORD_HASH` para no guardar password plano en `.env`

3. construir frontend:

```bash
cd frontend
npm install
npm run build
```

4. levantar stack completo:

```bash
cd deploy
docker compose --env-file ../.env -f docker-compose.production.yml up -d --build
```

Servicios incluidos:

- `postgres` con healthcheck
- `api` FastAPI + migraciones automáticas al iniciar
- `caddy` como web origin interno

En este modo `Granalia` publica solo `127.0.0.1:${GRANALIA_LOCAL_CADDY_PORT:-8088}` en la notebook.
El `cloudflared` de tu otro proyecto puede publicar un hostname nuevo apuntando a:

```text
http://host.docker.internal:8088
```

o al puerto que definas en `GRANALIA_LOCAL_CADDY_PORT`.

## Acceso PostgreSQL con DBeaver por SSH

`Granalia` publica PostgreSQL solo en localhost del host:

```text
127.0.0.1:${GRANALIA_LOCAL_POSTGRES_PORT:-5433}
```

Configuracion sugerida en DBeaver:

- Main / Host: `127.0.0.1`
- Main / Port: `5433`
- Main / Database: `granalia`
- Main / Username: `granalia`
- Main / Password: valor de `POSTGRES_PASSWORD`
- SSH / Use SSH Tunnel: habilitado
- SSH / Host: IP o dominio de la notebook
- SSH / Port: `22`
- SSH / User: tu usuario del servidor

Healthchecks utiles:

- `GET /health/live`
- `GET /health/ready`

## Logs y monitoreo basico

- logs estructurados por stdout en la API
- request logging con tiempo de respuesta en `X-Response-Time-Ms`
- readiness check con verificacion de base de datos y secreto de auth
- revisar contenedores:

```bash
cd deploy
docker compose --env-file ../.env -f docker-compose.production.yml logs -f api caddy postgres
```

## Backups

Script incluido:

```bash
sh deploy/scripts/backup_postgres.sh
```

Variables relevantes:

- `GRANALIA_BACKUP_DIR`
- `GRANALIA_BACKUP_RETENTION_DAYS`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

Ejemplo de cron diario:

```bash
0 3 * * * cd /ruta/a/Granalia && set -a && . ./.env && set +a && sh deploy/scripts/backup_postgres.sh >> backups/cron.log 2>&1
```

Recomendacion operativa:

- copiar backups fuera del servidor
- probar restore periodicamente
- no dejar Adminer expuesto en produccion

## Endpoints principales

- `GET /api/bootstrap`
- `GET /api/customers`
- `PUT /api/customers/{customer_key}`
- `GET /api/transports`
- `GET /api/discount-policies`
- `GET /api/products`
- `GET /api/invoices`
- `POST /api/invoices`
- `GET /api/invoices/{invoice_id}/xlsx`
- `POST /api/price-lists/upload`

## Notas

- el XLSX ya no se guarda en disco como almacenamiento principal; se genera en memoria y se persiste en PostgreSQL
- el catálogo activo sale de la base de datos
- subir un PDF de precios actualiza también el catálogo activo
- se eliminaron los artefactos locales de salida y la UI legacy en Python
