"""Keep the test suite away from the bot's real data.

The bot runs this suite at startup with its production environment, where
TINKI_DATA_DIR points at the live data folder. config.py reads that variable
once, at import time, so it has to be redirected here, before any test module
imports config. Without this, tests overwrote live conversations.json and
filled ai_memory.json with MagicMock users on every restart.
"""

import atexit
import os
import shutil
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="tinki-test-data-")
os.environ["TINKI_DATA_DIR"] = _TEST_DATA_DIR
atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)
