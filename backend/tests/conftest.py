import os
from pathlib import Path
from uuid import uuid4

import pytest


TEST_ROOT = Path(__file__).resolve().parent.parent / ".pytest-temp" / "import-app"
TEST_ROOT.mkdir(parents=True, exist_ok=True)

# Keep importing app.main side-effect free when a developer .env points at a
# remote PostgreSQL instance that is not running during unit tests.
os.environ["APP_DATABASE_URL"] = ""
os.environ["APP_DATA_DIR"] = str(TEST_ROOT)
os.environ["APP_MODEL_MODE"] = "mock"


@pytest.fixture
def tmp_path() -> Path:
    path = TEST_ROOT / "cases" / uuid4().hex
    path.mkdir(parents=True)
    return path
