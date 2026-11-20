"""Command line: ``kivi-ui create-admin | seed-demo | worker``."""

import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import select

from .config import get_settings
from .db import get_sessionmaker
from .models import Role, User, UserStatus
from .schemas import UserCreateIn
from .security import hash_password

DEMO_USERS = (
    ("admin", "admin@example.com", "王磊", Role.admin, UserStatus.active),
    ("analyst", "analyst@example.com", "李晓雯", Role.analyst, UserStatus.active),
    ("newcomer", "newcomer@example.com", "赵晨", Role.analyst, UserStatus.pending),
)


def _upsert(db, username, email, name, role, status, password) -> str:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        db.add(
            User(
                username=username,
                email=email,
                display_name=name,
                role=role,
                status=status,
                password_hash=hash_password(password),
            )
        )
        return "created"
    return "exists"


def create_admin(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password: ")
    try:
        data = UserCreateIn(
            username=args.username,
            email=args.email,
            display_name=args.name or args.username,
            password=password,
            role=Role.admin,
        )
    except ValidationError as error:
        print(error, file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        outcome = _upsert(
            db,
            data.username,
            str(data.email).lower(),
            data.display_name,
            Role.admin,
            UserStatus.active,
            data.password,
        )
        db.commit()
    print(f"admin '{data.username}': {outcome}")
    return 0


def seed_demo(args: argparse.Namespace) -> int:
    password = get_settings().demo_password
    if not password:
        print("Set KIVI_DEMO_PASSWORD (see backend/.env.example) to create demo accounts.", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        if getattr(args, "refresh", False):
            from .demo import refresh

            refresh(db)
            print("demo data: removed for re-seeding")
        for username, email, name, role, status in DEMO_USERS:
            print(f"user '{username}': {_upsert(db, username, email, name, role, status, password)}")
        db.commit()
        admin = db.scalar(select(User).where(User.username == "admin"))
        from .demo import seed_datasets

        for item in seed_datasets(db, admin):
            print(f"demo data: {item}")
        from .demo import seed_model

        analyst = db.scalar(select(User).where(User.username == "analyst"))
        for item in seed_model(db, admin, analyst):
            print(f"demo data: {item}")
        from .demo import seed_strategy

        for item in seed_strategy(db, admin, analyst):
            print(f"demo data: {item}")
        from .demo import seed_monitors

        for item in seed_monitors(db, admin, analyst):
            print(f"demo data: {item}")
    return 0


def worker(_: argparse.Namespace) -> int:
    """Run the background job worker in the foreground (when the API runs with KIVI_RUN_WORKER=false)."""
    from . import model_jobs  # noqa: F401  (registers job handlers)
    from .jobs import Worker
    from .monitoring import service  # noqa: F401  (registers the schedule tick)

    loop = Worker()
    print("kivi-ui worker: waiting for jobs (Ctrl+C to stop)")
    try:
        loop.run()
    except KeyboardInterrupt:
        loop.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kivi-ui")
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="create an active administrator")
    admin.add_argument("--username", required=True)
    admin.add_argument("--email", required=True)
    admin.add_argument("--name")
    admin.add_argument("--password", help="omit to be prompted")
    admin.set_defaults(func=create_admin)

    seed = commands.add_parser(
        "seed-demo", help="create demo accounts, data, models, strategies and monitors"
    )
    seed.add_argument("--refresh", action="store_true", help="remove demo content first and re-create it")
    seed.set_defaults(func=seed_demo)

    commands.add_parser("worker", help="run the background job worker").set_defaults(func=worker)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
