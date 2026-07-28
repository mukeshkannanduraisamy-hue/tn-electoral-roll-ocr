#!/usr/bin/env python
"""Administrative CLI for the OCR workspace.

Passwords are stored as bcrypt hashes and cannot be recovered -- only reset.
This is the supported way to regain access to a locked-out account, and the
only way to rotate credentials on a deployed instance where you cannot read
the first-boot log any more.

    python manage.py users
    python manage.py reset-password --username admin
    python manage.py reset-password --username admin --password 'S0me!Passphrase'
    python manage.py create-user --username reviewer
    python manage.py unlock --username admin
    python manage.py sessions --revoke-all

Schema changes go through alembic. The app upgrades itself at startup, so
these are for authoring and inspecting migrations rather than applying them:

    python manage.py db current
    python manage.py db revision -m "add elector status"
    python manage.py db upgrade
    python manage.py db downgrade -1
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import delete, select  # noqa: E402

from app.auth import hash_password, password_problems  # noqa: E402
from app.db import SessionRow, UserRow, init_db, session_scope  # noqa: E402


def _fmt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "—"


def _resolve_password(supplied: str | None, *, prompt: str) -> tuple[str, bool]:
    """Return (password, generated). Prompts interactively when possible."""
    if supplied:
        return supplied, False

    if sys.stdin.isatty():
        first = getpass.getpass(f"{prompt}: ")
        second = getpass.getpass("Confirm: ")
        if first != second:
            sys.exit("Passwords do not match.")
        if first:
            return first, False

    # Non-interactive and nothing supplied: generate rather than prompt into
    # a pipe that will never be answered.
    return secrets.token_urlsafe(12), True


def cmd_users(_args) -> None:
    with session_scope() as session:
        rows = session.execute(select(UserRow).order_by(UserRow.created_at)).scalars().all()
        if not rows:
            print("No users. Start the API once to create the initial admin.")
            return
        print(f"{'USERNAME':<20} {'ACTIVE':<7} {'FAILED':<7} {'LOCKED':<7} "
              f"{'CREATED':<17} LAST LOGIN")
        print("-" * 82)
        for u in rows:
            locked = "yes" if (u.locked_until and u.locked_until.replace(
                tzinfo=timezone.utc) > datetime.now(timezone.utc)) else "no"
            print(f"{u.username:<20} {'yes' if u.is_active else 'no':<7} "
                  f"{u.failed_attempts or 0:<7} {locked:<7} "
                  f"{_fmt(u.created_at):<17} {_fmt(u.last_login_at)}")


def cmd_reset_password(args) -> None:
    with session_scope() as session:
        user = session.execute(
            select(UserRow).where(UserRow.username == args.username)
        ).scalar_one_or_none()
        if user is None:
            sys.exit(f"No such user: {args.username!r}. Try: python manage.py users")

        password, generated = _resolve_password(
            args.password, prompt=f"New password for {args.username}"
        )
        problems = password_problems(password)
        if problems and not generated:
            sys.exit(f"Password {', and '.join(problems)}.")

        user.password_hash = hash_password(password)
        # A reset means the old credential is gone; any session opened with it
        # must go too, or a stolen cookie survives the very thing meant to
        # revoke it.
        revoked = session.execute(
            delete(SessionRow).where(SessionRow.user_id == user.id)
        ).rowcount or 0
        user.failed_attempts = 0
        user.locked_until = None

    print(f"\n  Password reset for {args.username!r}.")
    if generated:
        print(f"  password: {password}")
    print(f"  {revoked} existing session(s) revoked.")
    print("  Sign in, then change it from the UI if this was typed on a shared machine.\n")


def cmd_create_user(args) -> None:
    with session_scope() as session:
        if session.execute(
            select(UserRow).where(UserRow.username == args.username)
        ).scalar_one_or_none():
            sys.exit(f"User {args.username!r} already exists.")

        password, generated = _resolve_password(
            args.password, prompt=f"Password for {args.username}"
        )
        problems = password_problems(password)
        if problems and not generated:
            sys.exit(f"Password {', and '.join(problems)}.")

        session.add(UserRow(
            id=uuid.uuid4().hex[:12],
            username=args.username,
            password_hash=hash_password(password),
            display_name=args.display_name or args.username,
        ))

    print(f"\n  Created user {args.username!r}.")
    if generated:
        print(f"  password: {password}")
    print()


def cmd_unlock(args) -> None:
    with session_scope() as session:
        user = session.execute(
            select(UserRow).where(UserRow.username == args.username)
        ).scalar_one_or_none()
        if user is None:
            sys.exit(f"No such user: {args.username!r}")
        user.failed_attempts = 0
        user.locked_until = None
    print(f"  Unlocked {args.username!r}; failed-attempt counter cleared.")


def cmd_sessions(args) -> None:
    with session_scope() as session:
        if args.revoke_all:
            n = session.execute(delete(SessionRow)).rowcount or 0
            print(f"  Revoked {n} session(s). Everyone must sign in again.")
            return
        rows = session.execute(select(SessionRow)).scalars().all()
        print(f"  {len(rows)} active session(s).")
        for s in rows:
            print(f"    user={s.user_id}  expires={_fmt(s.expires_at)}  "
                  f"agent={(s.user_agent or '')[:48]}")


def cmd_db(args) -> None:
    from alembic import command

    from app.db import (
        _alembic_config,
        _run_alembic,
        alembic_session,
        is_under_alembic,
        schema_drift,
    )

    if args.db_command == "current":
        if not is_under_alembic():
            print("  Not under alembic yet. The next application start adopts it,")
            print("  or run: python manage.py db upgrade")
            return
        with alembic_session() as config:
            command.current(config, verbose=True)
        drift = schema_drift()
        if drift:
            print("\n  Schema differs from the models:")
            for table, columns in sorted(drift.items()):
                print(f"    {table}: {', '.join(columns)}")
            print("\n  Write a migration for these:")
            print("    python manage.py db revision -m 'describe the change'")
        else:
            print("  Schema matches the models.")

    elif args.db_command == "history":
        command.history(_alembic_config(), verbose=True)

    elif args.db_command == "upgrade":
        _run_alembic("upgrade", args.revision)
        print(f"  Upgraded to {args.revision}.")

    elif args.db_command == "downgrade":
        _run_alembic("downgrade", args.revision)
        print(f"  Downgraded to {args.revision}.")

    elif args.db_command == "revision":
        # Autogenerate opens its own connection: it reflects the database
        # while comparing it to the models, and doing that inside the
        # caller's open transaction deadlocks on SQLite.
        config = _alembic_config()
        command.revision(config, message=args.message, autogenerate=True)
        print("\n  Review the generated file before committing it. Autogenerate")
        print("  does not detect renames -- it sees a drop and an add, which")
        print("  discards the column's data.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR workspace administration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("users", help="List accounts").set_defaults(func=cmd_users)

    p = sub.add_parser("reset-password", help="Set a new password for an account")
    p.add_argument("--username", default="admin")
    p.add_argument("--password", default=None,
                   help="Omit to be prompted, or to have one generated")
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("create-user", help="Add an account")
    p.add_argument("--username", required=True)
    p.add_argument("--password", default=None)
    p.add_argument("--display-name", default="")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("unlock", help="Clear a lockout after failed logins")
    p.add_argument("--username", default="admin")
    p.set_defaults(func=cmd_unlock)

    p = sub.add_parser("sessions", help="Inspect or revoke sessions")
    p.add_argument("--revoke-all", action="store_true")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("db", help="Schema migrations")
    db_sub = p.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("current", help="Show the applied revision and any drift")
    db_sub.add_parser("history", help="List revisions")
    up = db_sub.add_parser("upgrade", help="Apply migrations")
    up.add_argument("revision", nargs="?", default="head")
    down = db_sub.add_parser("downgrade", help="Roll back migrations")
    down.add_argument("revision")
    rev = db_sub.add_parser("revision", help="Generate a migration from model changes")
    rev.add_argument("-m", "--message", required=True)
    p.set_defaults(func=cmd_db)

    args = parser.parse_args()
    # `db` subcommands manage the schema themselves; running the automatic
    # upgrade first would make `downgrade` a no-op and hide what `current`
    # is being asked to report.
    if args.command != "db":
        init_db()
    args.func(args)


if __name__ == "__main__":
    main()
