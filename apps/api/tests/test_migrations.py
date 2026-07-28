"""Schema migrations.

Exercised against real temporary SQLite files rather than the shared
development database, because the interesting cases are what happens to a
database in a *particular* state -- empty, or predating alembic -- and the
shared one is only ever in the current state.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.db import Base, schema_drift  # noqa: E402


@pytest.fixture()
def workspace():
    directory = Path(tempfile.mkdtemp(prefix="ocr-migrations-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def run(code: str, db_path: Path) -> subprocess.CompletedProcess:
    """Run a snippet against its own database, in its own process.

    A fresh interpreter per case is the point: `app.db` builds its engine at
    import time from the environment, so two databases cannot coexist inside
    one process.
    """
    import os

    env = dict(os.environ)
    env["OCR_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["PYTHONPATH"] = str(API_ROOT)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, env=env, cwd=str(API_ROOT), timeout=300,
    )


def check(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return result.stdout


# ---------------------------------------------------------------------------
# The three startup paths
# ---------------------------------------------------------------------------


def test_an_empty_database_is_built_by_migrations(workspace: Path):
    out = check(run(
        """
        from app.db import init_db, current_revision, schema_drift, _table_names
        init_db()
        print("REVISION", current_revision())
        print("DRIFT", schema_drift())
        print("TABLES", len(_table_names() - {"alembic_version"}))
        """,
        workspace / "fresh.sqlite",
    ))
    assert "DRIFT {}" in out
    assert "REVISION None" not in out
    # Every mapped table, built from the baseline alone.
    assert f"TABLES {len(Base.metadata.tables)}" in out


def test_a_pre_alembic_database_is_reconciled_and_stamped(workspace: Path):
    """The awkward case: schema exists, no version table, columns missing."""
    db = workspace / "legacy.sqlite"

    check(run(
        """
        from app.db import Base, engine, session_scope, FileRow
        Base.metadata.create_all(engine)
        with engine.begin() as c:
            c.exec_driver_sql("DROP INDEX ix_pages_page_type")
            c.exec_driver_sql("ALTER TABLE pages DROP COLUMN page_type")
            c.exec_driver_sql("DROP TABLE summaries")
        with session_scope() as s:
            s.add(FileRow(id="leg1", name="old.pdf", page_count=12))
        """,
        db,
    ))

    out = check(run(
        """
        from app.db import init_db, current_revision, schema_drift, session_scope, FileRow
        init_db()
        print("REVISION", current_revision())
        print("DRIFT", schema_drift())
        with session_scope() as s:
            print("FILES", [f.name for f in s.query(FileRow).all()])
        """,
        db,
    ))
    assert "DRIFT {}" in out, "adoption left the schema incomplete"
    assert "REVISION None" not in out, "database was not stamped"
    assert "FILES ['old.pdf']" in out, "adoption destroyed existing data"


def test_startup_is_idempotent(workspace: Path):
    out = check(run(
        """
        from app.db import init_db, current_revision
        init_db()
        first = current_revision()
        for _ in range(3):
            init_db()
        print("STABLE", first == current_revision() and first is not None)
        """,
        workspace / "repeat.sqlite",
    ))
    assert "STABLE True" in out


def test_an_empty_version_table_is_not_mistaken_for_a_stamped_database(
    workspace: Path,
):
    """Regression: several alembic commands create `alembic_version` as a
    side effect of connecting. Treating the table's presence as proof of a
    stamp sent a pre-alembic database down the upgrade path, where the
    baseline was replayed over tables that already existed."""
    db = workspace / "emptyversion.sqlite"

    check(run(
        """
        from app.db import Base, engine
        Base.metadata.create_all(engine)
        with engine.begin() as c:
            c.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        """,
        db,
    ))

    out = check(run(
        """
        from app.db import init_db, current_revision, is_under_alembic, schema_drift
        print("BEFORE", is_under_alembic())
        init_db()
        print("AFTER", current_revision() is not None)
        print("DRIFT", schema_drift())
        """,
        db,
    ))
    assert "BEFORE False" in out, "an empty version table must not count as stamped"
    assert "AFTER True" in out
    assert "DRIFT {}" in out


# ---------------------------------------------------------------------------
# What alembic buys over create_all
# ---------------------------------------------------------------------------


def test_a_column_rename_keeps_its_data_and_can_be_rolled_back(workspace: Path):
    """The operation `create_all` and the additive shim could never do."""
    db = workspace / "rename.sqlite"
    versions = API_ROOT / "migrations" / "versions"
    migration = versions / "ztest0001_rename.py"

    check(run(
        """
        from app.db import init_db, session_scope, VoterRow
        init_db()
        with session_scope() as s:
            s.add(VoterRow(id="v1", epic="ZHT0000001", name="Prema",
                           notes="checked twice"))
        """,
        db,
    ))

    migration.write_text(
        textwrap.dedent(
            '''
            """throwaway rename, created by the test suite"""
            from alembic import op

            revision = "ztest0001rename"
            down_revision = "a46b568717b8"
            branch_labels = None
            depends_on = None

            def upgrade() -> None:
                with op.batch_alter_table("voters") as batch:
                    batch.alter_column("notes", new_column_name="reviewer_notes")

            def downgrade() -> None:
                with op.batch_alter_table("voters") as batch:
                    batch.alter_column("reviewer_notes", new_column_name="notes")
            '''
        ).lstrip(),
        encoding="utf-8",
    )

    try:
        out = check(run(
            """
            from app.db import _run_alembic, engine, current_revision
            _run_alembic("upgrade", "ztest0001rename")
            with engine.begin() as c:
                print("RENAMED", [r[0] for r in
                      c.exec_driver_sql("select reviewer_notes from voters")])
            _run_alembic("downgrade", "a46b568717b8")
            print("BACK_AT", current_revision())
            with engine.begin() as c:
                print("RESTORED", [r[0] for r in
                      c.exec_driver_sql("select notes from voters")])
            """,
            db,
        ))
    finally:
        migration.unlink(missing_ok=True)
        shutil.rmtree(versions / "__pycache__", ignore_errors=True)

    assert "RENAMED ['checked twice']" in out, "rename lost the column's data"
    assert "BACK_AT a46b568717b8" in out
    assert "RESTORED ['checked twice']" in out, "rollback lost the column's data"


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def test_the_development_database_matches_the_models():
    """Catches a model change committed without a migration."""
    assert schema_drift() == {}
