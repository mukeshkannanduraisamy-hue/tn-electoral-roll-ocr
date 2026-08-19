#!/usr/bin/env python
"""Copy a PostgreSQL/Supabase OCR database into a local SQLite file.

The project runs on SQLite by design -- the service writes page images to the
same directory and runs its job queue in-process, so it is single-instance
whatever the database is, and Postgres added a network round trip to every
row for no structural gain. Bulk work paid for it heavily: promoting 31k
electors takes ~24s locally and is dominated by per-row latency against a
remote pooler.

Non-destructive by construction. It refuses to write into a file that already
holds data unless `--force` is given, so it cannot quietly overwrite a
database someone is still using.

    python scripts/migrate_supabase_to_sqlite.py \
        --source "postgresql://..." \
        --target data/ocr-from-supabase.sqlite

The source URL may also come from a dotenv file, which keeps the credential
off the command line and out of the shell history:

    python scripts/migrate_supabase_to_sqlite.py --source-env .env.backup-...

Rows are copied through the SQLAlchemy models rather than as raw SQL, so
JSON, boolean and timestamp columns are converted by the same code the
application uses to read them. Order follows foreign keys, and each table is
committed in batches so a large table does not build one enormous
transaction.

Reading the source needs a PostgreSQL driver, which the project no longer
depends on now that it runs on SQLite. Install one for the migration:

    pip install "psycopg[binary]"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base  # noqa: E402

#: Parents before children. `sorted_tables` already honours foreign keys, but
#: it is stated explicitly here because a wrong order fails as an integrity
#: error halfway through a copy rather than up front.
BATCH = 500


def source_url_from_env_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^\s*#?\s*OCR_DATABASE_URL=(postgres\S+)\s*$", text, re.M)
    if not match:
        raise SystemExit(f"No OCR_DATABASE_URL with a postgres:// value in {path}")
    return match.group(1).strip()


def redact(url: str) -> str:
    return re.sub(r"(://[^:]+:)[^@]+@", r"\1***@", url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--source",
                     help="database URL to read from; PostgreSQL normally, but "
                          "any SQLAlchemy URL works -- pointing it at a SQLite "
                          "file rebuilds that file onto the current schema")
    src.add_argument("--source-env", type=Path,
                     help="dotenv file holding OCR_DATABASE_URL")
    parser.add_argument("--target", required=True, type=Path,
                        help="SQLite file to write (created if absent)")
    parser.add_argument("--force", action="store_true",
                        help="allow writing into a target that already has rows")
    args = parser.parse_args()

    source_url = args.source or source_url_from_env_file(args.source_env)
    target_path = args.target if args.target.is_absolute() else REPO_ROOT / args.target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_url = f"sqlite:///{target_path.as_posix()}"

    print(f"source: {redact(source_url)}")
    print(f"target: {target_url}\n")

    # `connect_timeout` is a libpq setting; SQLite's driver rejects unknown
    # keywords outright, so it is only passed to the dialect that has it.
    connect_args = {} if source_url.startswith("sqlite") else {"connect_timeout": 30}
    source_engine = sa.create_engine(source_url, connect_args=connect_args)
    target_engine = sa.create_engine(target_url)

    # The schema is created from the models, not copied, so the SQLite file
    # gets SQLite-native column types instead of Postgres ones.
    Base.metadata.create_all(target_engine)

    tables = Base.metadata.sorted_tables
    source_inspector = sa.inspect(source_engine)
    present = set(source_inspector.get_table_names())

    if not args.force:
        with target_engine.connect() as conn:
            for table in tables:
                count = conn.execute(
                    sa.select(sa.func.count()).select_from(table)
                ).scalar() or 0
                if count:
                    raise SystemExit(
                        f"Target already holds {count} row(s) in {table.name}. "
                        f"Refusing to write into a database in use -- pass "
                        f"--force if that is really what you want."
                    )

    totals: dict[str, tuple[int, int]] = {}
    with Session(source_engine) as source, Session(target_engine) as target:
        for table in tables:
            if table.name not in present:
                print(f"  {table.name:22s} -- absent at source, skipped")
                continue

            # Select only the columns the source actually has. A database
            # whose schema has drifted from the models -- stamped at one
            # revision but carrying objects from another, which is what a
            # half-applied migration leaves behind -- would otherwise fail on
            # the first missing column and copy nothing. Columns absent at the
            # source take the target's default, which for every nullable
            # column added by a later migration is NULL, exactly as an upgrade
            # would have left them.
            source_columns = {c["name"] for c in source_inspector.get_columns(table.name)}
            usable = [c for c in table.columns if c.name in source_columns]
            missing = [c.name for c in table.columns if c.name not in source_columns]
            if missing:
                print(f"  {table.name:22s} -- source lacks {', '.join(missing)}; "
                      f"defaulted")

            rows = source.execute(sa.select(*usable)).mappings().all()
            copied = 0
            for start in range(0, len(rows), BATCH):
                chunk = [dict(r) for r in rows[start:start + BATCH]]
                if chunk:
                    target.execute(sa.insert(table), chunk)
                    copied += len(chunk)
                target.commit()
            totals[table.name] = (len(rows), copied)
            print(f"  {table.name:22s} {copied:>7d} row(s)")

    # `alembic_version` is not a model, so `Base.metadata` does not carry it
    # and the loop above cannot copy it. Without it the target looks like a
    # database predating alembic, and `init_db` would take its adopt-and-stamp
    # path -- meant for genuinely legacy files, not for a fresh copy.
    #
    # Stamped at HEAD rather than at whatever the source said. The schema here
    # was created from the models, so it is the current schema by
    # construction, whatever revision the source had reached. Copying a stale
    # revision across would leave alembic believing later migrations are
    # outstanding and trying to re-apply them to a schema that already has
    # them -- which is the failure this rebuild exists to escape ("index
    # ix_chat_threads_created_at already exists").
    from alembic.script import ScriptDirectory  # noqa: E402

    from app.db import _alembic_config  # noqa: E402

    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()

    with source_engine.connect() as conn:
        try:
            source_revision = conn.execute(
                sa.text("select version_num from alembic_version")
            ).scalar()
        except sa.exc.DatabaseError:
            source_revision = None

    with target_engine.begin() as conn:
        conn.execute(sa.text(
            "create table if not exists alembic_version ("
            "version_num varchar(32) not null primary key)"
        ))
        conn.execute(sa.text("delete from alembic_version"))
        conn.execute(
            sa.text("insert into alembic_version (version_num) values (:v)"),
            {"v": head},
        )
    note = "" if source_revision in (head, None) else f" (source was {source_revision})"
    print(f"  {'alembic_version':22s} {head}{note}")

    # Read back independently of the writing session, so the check reflects
    # what is actually on disk rather than what we believe we sent.
    print("\nverifying:")
    ok = True
    with target_engine.connect() as conn:
        for name, (read, _written) in totals.items():
            table = Base.metadata.tables[name]
            stored = conn.execute(
                sa.select(sa.func.count()).select_from(table)
            ).scalar() or 0
            flag = "ok" if stored == read else "MISMATCH"
            if stored != read:
                ok = False
            if read or stored:
                print(f"  {name:22s} source={read:<7d} target={stored:<7d} {flag}")

    size_mb = target_path.stat().st_size / 1048576
    print(f"\n{target_path} ({size_mb:.1f} MB)")
    if not ok:
        print("Row counts differ -- do NOT treat this copy as complete.")
        return 1
    print("Every table matches its source count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
