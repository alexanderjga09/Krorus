import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_json_data():
    return ["domain1.com", "domain2.org", "sub.domain3.net"]
