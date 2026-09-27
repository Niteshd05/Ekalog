import os
import sys
import tempfile
from pathlib import Path

# Isolated state + deterministic (model-free) labeling for tests.
os.environ["EKALOG_STATE_DIR"] = tempfile.mkdtemp(prefix="ekalog-test-")
os.environ["EKALOG_LLM_ENABLED"] = "0"
os.environ["EKALOG_SYSLOG_ENABLED"] = "0"
os.environ["EKALOG_DRIFT_MIN_EVENTS"] = "50"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA = Path(__file__).resolve().parent.parent / "data"


def read_lines(path: Path) -> list[str]:
    # bytes, not read_text(): universal newlines would split an embedded \r (the forgery under test)
    return [ln for ln in path.read_bytes().decode("utf-8").split("\n") if ln and not ln.startswith("#")]
