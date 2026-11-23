import os
import tempfile
from pathlib import Path

import config


def test_suite_writes_to_a_temporary_data_dir():
    data_dir = Path(config.DATA_DIR).resolve()
    assert data_dir == Path(os.environ["TINKI_DATA_DIR"]).resolve()
    assert data_dir.is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert data_dir != (Path(config.BASE_DIR) / "data").resolve()
