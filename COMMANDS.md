# Comandos Docker Produccion

Todos los comandos se corren desde la raiz del repo:

```bash
cd ~/proyectos/Granalia
```

## Levantar Servicios

Levantar API con rebuild:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d --build api
```

Levantar todo el stack:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d --build
```

Levantar solo Postgres:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d postgres
```

Levantar Caddy:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d caddy
```

Ver estado de servicios:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml ps
```

## Logs

Logs de API:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml logs -f api
```

Logs de Postgres:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml logs -f postgres
```

Logs de Caddy:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml logs -f caddy
```

Ultimas 200 lineas de API:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml logs --tail=200 api
```

## Debug

Entrar al contenedor API:

```bash
docker exec -it deploy-api-1 sh
```

Entrar a Python dentro de API:

```bash
docker exec -it deploy-api-1 python
```

Ver variables de entorno dentro de API:

```bash
docker exec -it deploy-api-1 env
```

Healthcheck local de API:

```bash
docker exec -it deploy-api-1 curl -fsS http://127.0.0.1:8000/health/live
```

Conectarse a Postgres con `psql`:

```bash
docker exec -it deploy-postgres-1 psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Si las variables no estan exportadas en la shell, usar los valores del `.env`:

```bash
docker exec -it deploy-postgres-1 psql -U granalia -d granalia
```

## Migraciones

Ejecutar migraciones manualmente:

```bash
docker exec -it deploy-api-1 python -m alembic -c alembic.ini upgrade head
```

Ver migracion actual:

```bash
docker exec -it deploy-api-1 python -m alembic -c alembic.ini current
```

Ver historial de migraciones:

```bash
docker exec -it deploy-api-1 python -m alembic -c alembic.ini history
```

## Scripts

### Importar PDFs historicos ARCA

Levantar API actualizada:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d --build api
```

Copiar PDFs al contenedor:

```bash
docker exec deploy-api-1 mkdir -p /tmp/preubas
docker cp docs/preubas/. deploy-api-1:/tmp/preubas/
```

Dry-run, sin escribir cambios:

```bash
docker exec -it deploy-api-1 python scripts/import_historical_arca_pdfs.py --pdf-dir /tmp/preubas --replace-historical --point-of-sale 2
```

Aplicar importacion historica:

```bash
docker exec -it deploy-api-1 python scripts/import_historical_arca_pdfs.py --pdf-dir /tmp/preubas --replace-historical --point-of-sale 2 --apply
```

Borrar solo historicos importados por el script, dry-run:

```bash
docker exec -it deploy-api-1 python scripts/import_historical_arca_pdfs.py --delete-historical
```

Borrar solo historicos importados por el script, aplicar:

```bash
docker exec -it deploy-api-1 python scripts/import_historical_arca_pdfs.py --delete-historical --apply
```

Debug de un PDF puntual:

```bash
docker exec -it deploy-api-1 python scripts/import_historical_arca_pdfs.py --debug-pdf /tmp/preubas/59.pdf --debug-limit 10000
```

Alternativa sin copiar PDFs, montando `docs/preubas` en un contenedor temporal:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml run --rm \
  -v "$(pwd)/docs/preubas:/docs/preubas:ro" \
  api python scripts/import_historical_arca_pdfs.py \
  --pdf-dir /docs/preubas \
  --replace-historical \
  --point-of-sale 2 \
  --apply
```

## Frontend

El servicio `caddy` sirve `frontend/dist`. Si cambia el frontend, reconstruir el dist fuera del contenedor y reiniciar Caddy:

```bash
npm --prefix frontend install
npm --prefix frontend run build
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d caddy
```

## Backups

Crear backup de Postgres:

```bash
docker exec deploy-postgres-1 pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > backup-granalia.sql
```

Crear backup con fecha:

```bash
docker exec deploy-postgres-1 pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "backup-granalia-$(date +%Y%m%d-%H%M%S).sql"
```

Restaurar backup:

```bash
docker exec -i deploy-postgres-1 psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < backup-granalia.sql
```

## Reiniciar Y Parar

Reiniciar API:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml restart api
```

Reiniciar todo:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml restart
```

Parar servicios sin borrar datos:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml down
```

Parar y borrar volumenes. Esto borra la base de datos:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml down -v
```

## Imagenes Y Limpieza

Rebuild limpio de API:

```bash
docker compose --env-file .env -f deploy/docker-compose.production.yml build --no-cache api
docker compose --env-file .env -f deploy/docker-compose.production.yml up -d api
```

Ver uso de disco Docker:

```bash
docker system df
```

Limpiar recursos no usados:

```bash
docker system prune
```
