from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from app.db.session import AsyncSessionLocal
from app.services.delivery_worker import DEFAULT_DELIVERY_BATCH_LIMIT, process_pending_notification_deliveries


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending VERIGRAPH notification deliveries.")
    parser.add_argument("--limit", type=int, default=DEFAULT_DELIVERY_BATCH_LIMIT, help="Maximum deliveries to process.")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    if args.limit < 1:
        print("Limit must be greater than zero.")
        return 1

    async with AsyncSessionLocal() as db:
        result = await process_pending_notification_deliveries(db, limit=args.limit)

    print(f"Processed: {result.processed}")
    print(f"Sent: {result.sent}")
    print(f"Failed: {result.failed}")
    return 0 if result.failed == 0 else 1


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(run(parse_args(argv))))


if __name__ == "__main__":
    main()
