"""Test-wide isolation.

The suite used to run against whatever `OCR_DATABASE_URL` pointed at -- which
in practice meant the working database. That is not a style objection: tests
here seed rows and delete them again, several clean up with filters like
`part_number == PART`, and a part number in a fixture is a part number that
exists in the real corpus. Running the suite emptied `data/ocr.sqlite` of
22,485 electors, and before that it emptied the hosted database it was pointed
at. Nothing failed while it happened; the tests passed and the data was gone.

So the database is redirected here, before `app.config` is imported anywhere.
`Settings` is a module-level singleton built at import time, and `app.db`
creates its engine at import time from that singleton, so this has to happen
in `conftest.py` -- by the time a test module runs its own import, the engine
already exists and pointing it somewhere else is too late.

`OCR_DATA_DIR` moves with it. Page images, uploads and photo crops are written
relative to it, and a test that writes a PNG into the real data directory is
the same class of problem in a quieter form.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# A directory per run, not per test: the engine is created once at import and
# cannot be repointed afterwards, so every test in the session shares it. They
# already assume that -- fixtures clean up after themselves rather than
# expecting a fresh database.
_TMP = Path(tempfile.mkdtemp(prefix="ocr-tests-"))

os.environ["OCR_DATA_DIR"] = str(_TMP)
os.environ["OCR_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.sqlite').as_posix()}"
# Keep the model cache shared. It is read-only here and re-downloading ~92 MB
# per run would be a slow way to gain nothing.
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(Path.home() / ".paddlex"))

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import database_url, init_db  # noqa: E402

# Fail loudly rather than run against the wrong database. A typo above, or an
# import that sneaks in earlier, would otherwise be invisible until something
# was already deleted.
_url = database_url()
if not (_url.startswith("sqlite:///") and _TMP.as_posix() in _url):
    raise RuntimeError(
        f"Test isolation failed: the suite is pointed at {_url!r}. "
        f"Refusing to run against a database outside {_TMP}."
    )
if Path(settings.data_dir) != _TMP:
    raise RuntimeError(
        f"Test isolation failed: data_dir is {settings.data_dir}, not {_TMP}."
    )

init_db()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_temp_workspace():
    """Remove the scratch database and data directory when the run ends."""
    yield
    shutil.rmtree(_TMP, ignore_errors=True)
