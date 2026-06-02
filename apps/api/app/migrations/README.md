# Migraciones

Este directorio contiene las migraciones Alembic para PostgreSQL.

## Ejecutar migraciones

Desde `apps/api`, con el entorno virtual activo:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://verigraph:verigraph@localhost:5432/verigraph"
..\..\.venv\Scripts\python.exe -m alembic upgrade head
```

## Crear una nueva migracion

```powershell
..\..\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "descripcion del cambio"
```

## Nota

El proyecto no crea tablas con helpers Python tipo `Base.metadata.create_all()`. El camino oficial es Alembic sobre PostgreSQL, porque deja historial de cambios y permite reproducir el esquema.
