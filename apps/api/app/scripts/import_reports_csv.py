import argparse
import asyncio
import csv
from pathlib import Path

from pydantic import ValidationError

from app.core.constants import EntityType
from app.db.session import AsyncSessionLocal
from app.schemas.report import ReportCreate
from app.services.reports import create_report


FIELD_ALIASES = {
    "entity_type": ("entity_type", "tipo", "tipo_entidad"),
    "entity_value": ("entity_value", "valor", "entidad", "entity"),
    "reason": ("reason", "motivo", "descripcion", "description"),
    "reporter_contact": ("reporter_contact", "contacto", "email", "correo"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa reportes desde un CSV.")
    parser.add_argument("csv_path", help="Ruta del CSV dentro del contenedor, por ejemplo /imports/reportes.csv")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de filas a importar. 0 importa todo.")
    parser.add_argument("--dry-run", action="store_true", help="Valida el archivo sin escribir en la base.")
    return parser.parse_args()


def pick(row: dict[str, str], field: str) -> str:
    for alias in FIELD_ALIASES[field]:
        value = row.get(alias)
        if value is not None and value.strip():
            return value.strip()
    return ""


def build_payload(row: dict[str, str], row_number: int) -> ReportCreate:
    entity_type = pick(row, "entity_type").lower()
    if not entity_type:
        entity_type = EntityType.OTHER.value

    reason = pick(row, "reason")
    if not reason:
        reason = f"Importacion masiva fila {row_number}. Pendiente de revision."

    return ReportCreate(
        entity_type=EntityType(entity_type),
        entity_value=pick(row, "entity_value"),
        reason=reason,
        reporter_contact=pick(row, "reporter_contact") or None,
    )


async def import_csv(path: Path, *, limit: int, dry_run: bool) -> int:
    imported = 0
    failed = 0

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise SystemExit("El CSV no tiene cabeceras.")

        async with AsyncSessionLocal() as db:
            for row_number, row in enumerate(reader, start=2):
                if limit and imported >= limit:
                    break

                try:
                    payload = build_payload(row, row_number)
                    if not dry_run:
                        await create_report(db, payload, source="bulk_import")
                    imported += 1
                    if imported % 100 == 0:
                        print(f"Importados {imported} reportes...")
                except (ValueError, ValidationError) as exc:
                    failed += 1
                    print(f"Fila {row_number} omitida: {exc}")
                except Exception as exc:
                    failed += 1
                    print(f"Fila {row_number} fallo: {exc}")

    print(f"Listo. Importados: {imported}. Fallidos: {failed}. Dry run: {dry_run}.")
    return 1 if failed else 0


def main() -> None:
    args = parse_args()
    path = Path(args.csv_path)
    if not path.exists():
        raise SystemExit(f"No existe el archivo: {path}")
    raise SystemExit(asyncio.run(import_csv(path, limit=args.limit, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
