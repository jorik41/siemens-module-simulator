import importlib
import sys
from pathlib import Path

import pytest


def test_import_without_snap7():
    try:
        import snap7  # type: ignore  # pragma: no cover
    except ModuleNotFoundError:
        snap7_installed = False
    else:  # pragma: no cover - environment with snap7
        snap7_installed = True

    if snap7_installed:  # pragma: no cover - skip when dependency present
        pytest.skip("snap7 installed")

    sys.modules.pop("plc_tester_gui", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    mod = importlib.import_module("plc_tester_gui")
    assert mod.snap7 is None
    conn = mod.PLCConnection()
    with pytest.raises(RuntimeError):
        conn.connect("127.0.0.1")
