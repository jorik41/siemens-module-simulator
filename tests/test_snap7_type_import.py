import importlib
import sys
from pathlib import Path
import types
import enum

def test_import_with_new_snap7(monkeypatch):
    snap7_mod = types.ModuleType("snap7")
    snap7_mod.__path__ = []  # mark as package
    util_mod = types.ModuleType("snap7.util")
    def _dummy(*args, **kwargs):
        return 0
    for name in (
        "get_bool",
        "get_dint",
        "get_dword",
        "get_int",
        "get_real",
        "get_word",
        "set_bool",
        "set_dint",
        "set_dword",
        "set_int",
        "set_real",
        "set_word",
    ):
        setattr(util_mod, name, _dummy)
    type_mod = types.ModuleType("snap7.type")
    class Areas(enum.IntEnum):
        MK = 131
        DB = 132
    type_mod.Areas = Areas
    client_mod = types.ModuleType("snap7.client")
    class Client:
        def read_area(self, area, db, start, size):
            self.last_area = area
            return b"\x00" * size
        def db_read(self, db, start, size):
            return b"\x00" * size
        def db_write(self, db, start, data):
            pass
    client_mod.Client = Client
    snap7_mod.util = util_mod
    snap7_mod.type = type_mod
    snap7_mod.client = client_mod
    modules = {
        "snap7": snap7_mod,
        "snap7.util": util_mod,
        "snap7.type": type_mod,
        "snap7.client": client_mod,
    }
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    sys.modules.pop("plc_tester_gui", None)
    mod = importlib.import_module("plc_tester_gui")
    conn = mod.PLCConnection()
    conn.read(1, 0, 1, "M")
    assert conn.client.last_area == mod.areas["MK"]
