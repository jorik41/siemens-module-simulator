import pytest


def _create_root():
    """Attempt to create a Tk root, skipping test if not available."""
    try:
        import tkinter as tk
    except Exception:  # pragma: no cover - tkinter may be missing entirely
        pytest.skip("tkinter not available")

    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - no display
        pytest.skip("Tk display not available")
    root.withdraw()
    return tk, root


def test_start_address_updates_variable_and_type():
    tk, root = _create_root()

    from plc_tester_gui import StepEditor

    layout = {
        "1": {
            "name": "DB1",
            "variables": [
                {"name": "A", "offset": 0, "type": "INT"},
                {"name": "Flag", "offset": 1, "bit": 0, "type": "BOOL"},
            ],
        }
    }

    editor = StepEditor(root, db_layout=layout)
    editor.db_combo.set("1:DB1")
    editor._on_db_selected(None)

    editor.start_var.set("0")
    assert editor.var_combo.get() == "A"
    assert editor.type_var.get() == "INT"

    editor.start_var.set("1.0")
    assert editor.var_combo.get() == "Flag"
    assert editor.type_var.get() == "BOOL"

    editor.destroy()
    root.destroy()

