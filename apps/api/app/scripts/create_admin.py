from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from getpass import getpass

from app.db.session import AsyncSessionLocal
from app.services.users import InvalidPasswordError, UserAlreadyExistsError, create_admin_user


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a VERIGRAPH admin user.")
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument("--password", help="Admin password. If omitted, it is requested interactively.")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    password = args.password or getpass("Admin password: ")

    async with AsyncSessionLocal() as db:
        try:
            user = await create_admin_user(db, email=args.email, password=password)
        except UserAlreadyExistsError:
            print(f"Admin user already exists: {args.email.strip().lower()}")
            return 1
        except InvalidPasswordError as exc:
            print(str(exc))
            return 1

    print(f"Admin user created: {user.email}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(run(parse_args(argv))))


if __name__ == "__main__":
    main()
