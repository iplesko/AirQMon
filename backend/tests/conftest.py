from __future__ import annotations

import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
TEST_TMP_DIR = BACKEND_DIR / "tests" / "_tmp"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db import get_conn, init_db


@pytest.fixture
def test_tmp_dir() -> Path:
    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    case_dir = TEST_TMP_DIR / uuid4().hex
    case_dir.mkdir()
    try:
        yield case_dir
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


@pytest.fixture
def db_path(test_tmp_dir: Path) -> Path:
    return test_tmp_dir / "airqmon-test.db"


@pytest.fixture
def conn(db_path: Path):
    connection = get_conn(str(db_path))
    init_db(connection)
    try:
        yield connection
    finally:
        connection.close()
