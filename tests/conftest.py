import os
import tempfile

os.environ["SAFETRACE_DATA_DIR"] = tempfile.mkdtemp(prefix="safetrace-test-")
os.environ["SAFETRACE_OFFLINE"] = "1"

import pytest

from backend import storage


@pytest.fixture(autouse=True)
def database():
    storage.init()
