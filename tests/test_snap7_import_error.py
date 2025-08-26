import importlib
import builtins
import sys
from pathlib import Path

import pytest


def test_snap7_import_error_propagates(monkeypatch):
    """Import errors other than missing module should not be masked."""
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "snap7":
            raise OSError("broken snap7")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("plc_tester_gui", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    with pytest.raises(OSError, match="broken snap7"):
        importlib.import_module("plc_tester_gui")
