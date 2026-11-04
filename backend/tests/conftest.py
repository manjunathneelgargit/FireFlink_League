import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="ffl_test_")
os.environ["DISABLE_GSHEET_SYNC"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.migrate import ensure_default_team  # noqa: E402


@pytest.fixture()
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ensure_default_team(engine)
    yield
