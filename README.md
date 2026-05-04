# Granalia

Aplicacion web para gestionar pedidos, clientes, transportes, productos, listas de precios y facturas de Granalia.

El sistema esta compuesto por una API FastAPI, una web React/Vite y una base PostgreSQL. La informacion operativa se persiste en base de datos y los comprobantes XLSX/PDF se generan desde la API.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL, OpenPyXL, ReportLab, pypdf.
- Frontend: React 18, React Router, Vite y Tailwind CSS.
- Base de datos: PostgreSQL 16.
- Despliegue: Docker Compose y Caddy.

## Funcionalidades

- Inicio de sesion con cookie HTTP-only, token CSRF y roles `admin` / `operator`.
- Creacion, edicion, descarga y eliminacion de facturas.
- Descarga de facturas en XLSX y PDF.
- Historial de facturas con estadisticas para administradores.
- Gestion de clientes, productos, presentaciones y transportes.
- Carga de listas de precios PDF y actualizacion del catalogo activo.
- Reglas de bonificacion automaticas por cliente.
- Healthchecks y logging estructurado para operacion.

## Estructura

```text
backend/                 API FastAPI, dominio, servicios, repositorios y migraciones
frontend/                Aplicacion React/Vite
deploy/                  Dockerfiles, Caddy y scripts operativos
docker-compose.postgres.yml
.env.example             Variables base para produccion
```

## Datos principales

Tablas operativas principales:

- `app_users`
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

- cada cliente puede tener transporte y politica de descuento por defecto;
- cada producto tiene una o mas presentaciones;
- cada factura pertenece a un cliente y tiene items asociados;
- cada item referencia producto y presentacion;
- cada lista PDF queda registrada y puede alimentar el catalogo activo.

## Requisitos

- Python 3.11+.
- Node.js 18+.
- Docker y Docker Compose.
- PostgreSQL local o el servicio incluido en `docker-compose.postgres.yml`.

## Desarrollo Local

### 1. Levantar PostgreSQL

```bash
docker compose -f docker-compose.postgres.yml up -d
```

Adminer queda disponible en `http://127.0.0.1:8082/`.

Credenciales locales por defecto:

- servidor: `postgres`
- usuario: `granalia`
- clave: `granalia`
- base: `granalia`

### 2. Preparar y correr la API

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m alembic -c alembic.ini upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

API local:

- base: `http://127.0.0.1:8000`
- docs: `http://127.0.0.1:8000/docs`
- health live: `http://127.0.0.1:8000/health/live`
- health ready: `http://127.0.0.1:8000/health/ready`

### 3. Preparar y correr la web

```bash
cd frontend
npm install
npm run dev
```

Web local: `http://127.0.0.1:5173`.

Por defecto, cuando Vite corre en el puerto `5173`, el frontend apunta a `http://<host>:8000`. Para usar otra API:

```bash
VITE_API_URL=http://127.0.0.1:8000 npm run dev
```

### Cookies Seguras En Local

La cookie de sesion usa `Secure` por defecto. Para desarrollo HTTP local sin Caddy, desactivala temporalmente antes de iniciar la API:

```bash
export GRANALIA_SECURE_COOKIES=false
```

No desactivar cookies seguras en produccion.

## Autenticacion

La primera vez que la API inicia con la tabla `app_users` vacia, crea un usuario inicial.

Opciones recomendadas:

- definir `GRANALIA_AUTH_USERNAME`, `GRANALIA_AUTH_PASSWORD` y `GRANALIA_AUTH_ROLE` antes de iniciar la API;
- o definir `GRANALIA_AUTH_PASSWORD_HASH` para no guardar password plano en variables de entorno;
- o usar el password generado que la API imprime por stdout en el primer arranque.

Para actualizar credenciales manualmente:

```bash
cd backend
python3 set_admin_password.py
```

Roles disponibles:

- `admin`: acceso completo, gestion y estadisticas.
- `operator`: acceso operativo limitado al historial visible y creacion/descarga de facturas permitidas.

## Variables De Entorno

Archivo base:

```bash
cp .env.example .env
```

Variables principales:

- `GRANALIA_ENV`: `development` o `production`.
- `GRANALIA_POSTGRES_URL`: URL SQLAlchemy para PostgreSQL.
- `GRANALIA_SESSION_SECRET`: secreto de sesion, obligatorio y de 32+ caracteres en produccion.
- `GRANALIA_SECURE_COOKIES`: mantiene cookies seguras cuando vale `true`.
- `GRANALIA_ALLOWED_ORIGINS`: origenes permitidos por CORS, separados por coma.
- `GRANALIA_AUTH_USERNAME`: usuario inicial.
- `GRANALIA_AUTH_PASSWORD`: password inicial en texto plano.
- `GRANALIA_AUTH_PASSWORD_HASH`: hash inicial alternativo.
- `GRANALIA_AUTH_ROLE`: rol del usuario inicial (`admin` u `operator`).
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: configuracion del contenedor PostgreSQL.

## Build Del Frontend

```bash
cd frontend
npm install
npm run build
```

El build queda en `frontend/dist`.

## Caddy Local

Configuracion:

- `deploy/Caddyfile`
- `deploy/docker-compose.caddy.yml`

Flujo recomendado:

```bash
cd frontend
npm install
npm run build
```

```bash
cd backend
python3 -m alembic -c alembic.ini upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd deploy
docker compose -f docker-compose.caddy.yml up -d
```

Con `.env.example`, Caddy escucha en HTTP por defecto: `http://localhost`.

Para usar HTTPS local, configurar un sitio compatible con TLS en `GRANALIA_CADDY_SITE` y acceder por ese hostname. Si se usa HTTP, iniciar la API con `GRANALIA_SECURE_COOKIES=false` para que el navegador acepte la cookie de sesion.

Caddy sirve el frontend estatico y proxya estos paths a FastAPI:

- `/api/*`
- `/health/*`
- `/docs*`
- `/redoc*`
- `/openapi.json`

Tambien agrega headers basicos de endurecimiento como `HSTS`, `nosniff`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`.

## Produccion

### 1. Crear configuracion

```bash
cp .env.example .env
```

Completar valores reales:

- `GRANALIA_SESSION_SECRET` con 32+ caracteres.
- `POSTGRES_PASSWORD` fuerte.
- `GRANALIA_POSTGRES_URL` apuntando al servicio `postgres`.
- `GRANALIA_ALLOWED_ORIGINS` con el dominio real.
- `GRANALIA_AUTH_USERNAME` y `GRANALIA_AUTH_ROLE`.
- `GRANALIA_AUTH_PASSWORD_HASH` o `GRANALIA_AUTH_PASSWORD` para el usuario inicial.

### 2. Construir frontend

```bash
cd frontend
npm install
npm run build
```

### 3. Levantar stack

```bash
cd deploy
docker compose --env-file ../.env -f docker-compose.production.yml up -d --build
```

Servicios incluidos:

- `postgres` con healthcheck y puerto publicado solo en localhost.
- `api` con FastAPI y migraciones automaticas al iniciar.
- `caddy` como origen web interno.

Puertos locales por defecto:

- Web/Caddy: `127.0.0.1:${GRANALIA_LOCAL_CADDY_PORT:-8088}`.
- PostgreSQL: `127.0.0.1:${GRANALIA_LOCAL_POSTGRES_PORT:-5433}`.

Si se publica con `cloudflared` u otro proxy externo, apuntar el hostname a:

```text
http://host.docker.internal:8088
```

o al puerto configurado en `GRANALIA_LOCAL_CADDY_PORT`.

## PostgreSQL Con DBeaver Por SSH

Configuracion sugerida:

- Main / Host: `127.0.0.1`
- Main / Port: `5433`
- Main / Database: `granalia`
- Main / Username: `granalia`
- Main / Password: valor de `POSTGRES_PASSWORD`
- SSH / Use SSH Tunnel: habilitado
- SSH / Host: IP o dominio del servidor
- SSH / Port: `22`
- SSH / User: usuario del servidor

No exponer PostgreSQL ni Adminer publicamente en produccion.

## Logs Y Monitoreo

Healthchecks:

- `GET /health/live`
- `GET /health/ready`

Logs:

- la API escribe logs por stdout;
- cada request agrega `X-Response-Time-Ms`;
- `GRANALIA_LOG_JSON=true` habilita logs JSON.

Comando util:

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

Recomendaciones:

- copiar backups fuera del servidor;
- probar restores periodicamente;
- no dejar Adminer expuesto en produccion.

## Endpoints Principales

Autenticacion:

- `GET /api/auth/session`
- `POST /api/auth/login`
- `POST /api/auth/logout`

Datos base:

- `GET /api/bootstrap`
- `GET /api/customers`
- `POST /api/customers`
- `PUT /api/customers/{customer_id}`
- `DELETE /api/customers/{customer_id}`
- `GET /api/transports`
- `POST /api/transports`
- `PUT /api/transports/{transport_id}`
- `DELETE /api/transports/{transport_id}`
- `GET /api/products`
- `POST /api/products`
- `POST /api/products/{product_id}/offerings`
- `DELETE /api/products/{product_id}`

Facturas:

- `GET /api/invoices`
- `GET /api/invoices/stats/items`
- `GET /api/invoices/{invoice_id}`
- `GET /api/invoices/{invoice_id}/xlsx`
- `GET /api/invoices/{invoice_id}/pdf`
- `POST /api/invoices`
- `PUT /api/invoices/{invoice_id}`
- `DELETE /api/invoices/{invoice_id}`

Listas de precios:

- `GET /api/price-lists`
- `POST /api/price-lists/upload`
- `PATCH /api/price-lists/{price_list_id}`
- `GET /api/price-lists/{price_list_id}/catalog`
- `DELETE /api/price-lists/{price_list_id}`

## Notas Operativas

- Ejecutar migraciones antes de iniciar la API en desarrollo.
- En produccion, el contenedor `api` corre migraciones al arrancar.
- El XLSX no se usa como almacenamiento principal; se genera desde datos persistidos en PostgreSQL.
- La lista de precios activa sale de la base de datos.
- Subir un PDF de precios puede actualizar el catalogo activo.
