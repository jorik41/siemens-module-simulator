"""
A simple GUI to create and run PLC test plans using Snap7.
"""

import json
import time
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Union, Callable

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import snap7
from snap7.util import (
    get_bool,
    get_dint,
    get_dword,
    get_int,
    get_real,
    get_word,
    set_bool,
    set_dint,
    set_dword,
    set_int,
    set_real,
    set_word,
)


@dataclass
class TestStep:
    """Single action within a test case."""
    description: str
    db_number: int
    start: int | str | List[int | str]
    data_type: str | List[str]
    write: Any | List[Any] | None = None
    expected: Any | List[Any] | None = None
    delay_ms: int | None = None


@dataclass
class TestCase:
    """Collection of steps to validate a module behaviour."""
    name: str
    steps: List[TestStep] = field(default_factory=list)


@dataclass
class ModulePlan:
    """Group of test cases for a specific module."""
    name: str
    tests: List[TestCase] = field(default_factory=list)


@dataclass
class TestPlan:
    """Top level structure representing an entire plan."""
    modules: List[ModulePlan] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"modules": [asdict(m) for m in self.modules]}

    @classmethod
    def from_dict(cls, data: dict) -> "TestPlan":
        modules: List[ModulePlan] = []
        for m in data.get("modules", []):
            tests: List[TestCase] = []
            for t in m.get("tests", []):
                steps = [TestStep(**s) for s in t.get("steps", [])]
                tests.append(TestCase(name=t["name"], steps=steps))
            modules.append(ModulePlan(name=m["name"], tests=tests))
        return cls(modules=modules)


TYPE_FUNCS = {
    "INT": (2, set_int, get_int),
    "DINT": (4, set_dint, get_dint),
    "WORD": (2, set_word, get_word),
    "DWORD": (4, set_dword, get_dword),
    "REAL": (4, set_real, get_real),
}


def run_plan(plan: TestPlan, ip: str = "127.0.0.1", rack: int = 0, slot: int = 1) -> None:
    """Run ``plan`` against the specified PLC."""
    conn = PLCConnection()
    conn.connect(ip, rack, slot)
    try:
        for module in plan.modules:
            for test in module.tests:
                _run_test(conn, test)
    finally:
        conn.disconnect()


def run_json_plan(
    data: Union[str, Dict[str, Any]],
    ip: str = "127.0.0.1",
    rack: int = 0,
    slot: int = 1,
) -> None:
    """Run a test plan described as JSON."""

    if isinstance(data, str):
        with open(data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    plan = TestPlan.from_dict(data)
    run_plan(plan, ip=ip, rack=rack, slot=slot)


def _run_test(conn: "PLCConnection", test: TestCase) -> None:
    """Execute a single :class:`TestCase` using ``conn``."""

    for step in test.steps:
        starts = step.start if isinstance(step.start, list) else [step.start]
        types = step.data_type if isinstance(step.data_type, list) else [step.data_type]
        if len(types) == 1 and len(starts) > 1:
            types = types * len(starts)
        writes = step.write if isinstance(step.write, list) else ([step.write] if step.write is not None else [])
        expecteds = (
            step.expected if isinstance(step.expected, list) else ([step.expected] if step.expected is not None else [])
        )

        if step.delay_ms:
            time.sleep(step.delay_ms / 1000.0)

        for idx, start in enumerate(starts):
            dtype = types[idx]
            w = writes[idx] if idx < len(writes) else None
            e = expecteds[idx] if idx < len(expecteds) else None
            if dtype == "BOOL":
                byte_str, bit_str = str(start).split(".")
                byte_idx, bit_idx = int(byte_str), int(bit_str)
                if w is not None:
                    cur = bytearray(conn.read(step.db_number, byte_idx, 1))
                    set_bool(cur, 0, bit_idx, bool(w))
                    conn.write(step.db_number, byte_idx, bytes(cur))
                if e is not None:
                    data = conn.read(step.db_number, byte_idx, 1)
                    val = get_bool(data, 0, bit_idx)
                    if val != bool(e):
                        raise AssertionError(
                            f"{step.description} at {start}: expected {e} got {val}"
                        )
            elif dtype == "BYTE":
                addr = int(start)
                if w is not None:
                    conn.write(step.db_number, addr, bytes([int(w)]))
                if e is not None:
                    data = conn.read(step.db_number, addr, 1)
                    val = data[0]
                    if val != int(e):
                        raise AssertionError(
                            f"{step.description} at {start}: expected {e} got {val}"
                        )
            else:
                size, set_func, get_func = TYPE_FUNCS[dtype]
                addr = int(start)
                if w is not None:
                    buf = bytearray(size)
                    set_func(buf, 0, w)
                    conn.write(step.db_number, addr, bytes(buf))
                if e is not None:
                    data = conn.read(step.db_number, addr, size)
                    val = get_func(data, 0)
                    ok = abs(val - float(e)) < 1e-6 if dtype == "REAL" else val == e
                    if not ok:
                        raise AssertionError(
                            f"{step.description} at {start}: expected {e} got {val}"
                        )


class StepEditor(tk.Toplevel):
    """Dialog to create or edit a :class:`TestStep`.

    The editor displays all fields at once so users can quickly define a
    step without navigating multiple popups. Inputs are validated before
    the resulting :class:`TestStep` is returned.
    """

    def __init__(
        self, master: tk.Misc, step: TestStep | None = None, title: str = "Step"
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: TestStep | None = None

        self.description_var = tk.StringVar()
        self.db_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.type_var = tk.StringVar()
        self.write_var = tk.StringVar()
        self.expected_var = tk.StringVar()
        self.delay_var = tk.StringVar()

        if step:
            self.description_var.set(step.description)
            self.db_var.set(str(step.db_number))
            if isinstance(step.start, list):
                self.start_var.set(",".join(str(s) for s in step.start))
            else:
                self.start_var.set(str(step.start))
            if isinstance(step.data_type, list):
                self.type_var.set(",".join(step.data_type))
            else:
                self.type_var.set(step.data_type)
            if step.write is not None:
                if isinstance(step.write, list):
                    self.write_var.set(",".join(str(v) for v in step.write))
                else:
                    self.write_var.set(str(step.write))
            if step.expected is not None:
                if isinstance(step.expected, list):
                    self.expected_var.set(",".join(str(v) for v in step.expected))
                else:
                    self.expected_var.set(str(step.expected))
            if step.delay_ms is not None:
                self.delay_var.set(str(step.delay_ms))

        frm = ttk.Frame(self)
        frm.pack(padx=10, pady=10)

        ttk.Label(frm, text="Description").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.description_var, width=40).grid(row=0, column=1)

        ttk.Label(frm, text="DB number").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.db_var, width=10).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Start address(es)").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.start_var, width=20).grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Data type(s)").grid(row=3, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.type_var, width=20).grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Write values (comma)").grid(row=4, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.write_var, width=30).grid(
            row=4, column=1, sticky="w"
        )

        ttk.Label(frm, text="Expected values (comma)").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Entry(frm, textvariable=self.expected_var, width=30).grid(
            row=5, column=1, sticky="w"
        )

        ttk.Label(frm, text="Delay ms").grid(row=6, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.delay_var, width=10).grid(
            row=6, column=1, sticky="w"
        )

        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=7, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frm, text="OK", command=self._on_ok).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frm, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=5)

        self.grab_set()
        self.wait_visibility()
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_ok(self) -> None:
        try:
            desc = self.description_var.get().strip()
            if not desc:
                raise ValueError("Description required")
            db = int(self.db_var.get())
            start_tokens = [s.strip() for s in self.start_var.get().split(",") if s.strip()]
            if not start_tokens:
                raise ValueError("Start address required")
            starts: List[int | str] = []
            for tok in start_tokens:
                if "." in tok:
                    byte, bit = tok.split(".")
                    starts.append(f"{int(byte)}.{int(bit)}")
                else:
                    starts.append(int(tok))

            type_tokens = [t.strip().upper() for t in self.type_var.get().split(",") if t.strip()]
            if not type_tokens:
                raise ValueError("Data type required")
            if len(type_tokens) == 1 and len(starts) > 1:
                type_tokens = type_tokens * len(starts)
            if len(type_tokens) != len(starts):
                raise ValueError("Data types must match start addresses")

            write_tokens = [w.strip() for w in self.write_var.get().split(",") if w.strip()]
            expected_tokens = [e.strip() for e in self.expected_var.get().split(",") if e.strip()]
            write_vals: List[Any] = []
            expected_vals: List[Any] = []
            if write_tokens:
                if len(write_tokens) != len(starts):
                    raise ValueError("Write values must match start addresses")
                write_vals = [self._parse_value(tok, type_tokens[i]) for i, tok in enumerate(write_tokens)]
            if expected_tokens:
                if len(expected_tokens) != len(starts):
                    raise ValueError("Expected values must match start addresses")
                expected_vals = [self._parse_value(tok, type_tokens[i]) for i, tok in enumerate(expected_tokens)]

            delay_ms = int(self.delay_var.get()) if self.delay_var.get().strip() else None
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        start_val: int | str | List[int | str] = starts[0] if len(starts) == 1 else starts
        type_val: str | List[str] = type_tokens[0] if len(type_tokens) == 1 else type_tokens
        write_val: Any | List[Any] | None = None
        if write_vals:
            write_val = write_vals[0] if len(write_vals) == 1 else write_vals
        expected_val: Any | List[Any] | None = None
        if expected_vals:
            expected_val = expected_vals[0] if len(expected_vals) == 1 else expected_vals

        self.result = TestStep(
            desc, db, start_val, type_val, write_val, expected_val, delay_ms
        )
        self.destroy()

    def _parse_value(self, token: str, dtype: str) -> Any:
        try:
            if dtype == "REAL":
                return float(token)
            if dtype == "BOOL":
                return token.lower() in {"1", "true", "t", "yes"}
            return int(token)
        except ValueError as exc:  # pragma: no cover - simple validation
            raise ValueError(f"Invalid {dtype} value: {token}") from exc


class PlanJsonEditor(tk.Toplevel):
    """JSON plan editor with live validation and templates."""

    MODULE_TEMPLATE = '{\n  "name": "Module Name",\n  "tests": []\n}'
    TEST_TEMPLATE = '{\n  "name": "Test Name",\n  "steps": []\n}'
    STEP_TEMPLATE = (
        '{\n  "description": "Step description",\n'
        '  "db_number": 1,\n'
        '  "start": 0,\n'
        '  "data_type": "INT",\n'
        '  "write": 0,\n'
        '  "expected": 0,\n'
        '  "delay_ms": 0\n}'
    )

    KEYWORDS = [
        "modules",
        "tests",
        "steps",
        "name",
        "description",
        "db_number",
        "start",
        "data_type",
        "write",
        "expected",
        "delay_ms",
    ]

    def __init__(self, gui: "PLCTestGUI") -> None:
        super().__init__(gui.root)
        self.gui = gui
        self.gui.json_editor = self
        self.title("Plan JSON Editor")

        self.text = tk.Text(self, width=80, height=25)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.bind("<KeyPress>", self._handle_keypress)
        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<Tab>", self._autocomplete)
        self.suggestions: List[str] = []

        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill=tk.X)
        ttk.Button(btn_frm, text="Run", command=self._run).pack(
            side=tk.LEFT, padx=5, pady=5
        )
        ttk.Button(btn_frm, text="Insert Module", command=self._insert_module).pack(
            side=tk.LEFT, padx=5, pady=5
        )
        ttk.Button(btn_frm, text="Insert Test", command=self._insert_test).pack(
            side=tk.LEFT, padx=5, pady=5
        )
        ttk.Button(btn_frm, text="Insert Step", command=self._insert_step).pack(
            side=tk.LEFT, padx=5, pady=5
        )
        ttk.Button(btn_frm, text="Close", command=self.destroy).pack(
            side=tk.LEFT, padx=5, pady=5
        )

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(
            fill=tk.X, padx=5
        )

        self.update_from_plan()

    def destroy(self) -> None:  # type: ignore[override]
        self.gui.json_editor = None
        super().destroy()

    def update_from_plan(self) -> None:
        """Refresh the text widget from the GUI's current plan."""
        plan_json = json.dumps(self.gui.plan.to_dict(), indent=2)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", plan_json)
        self._validate()

    def _insert_module(self) -> None:
        self.text.insert(tk.INSERT, self.MODULE_TEMPLATE)
        self._on_key_release(None)

    def _insert_test(self) -> None:
        self.text.insert(tk.INSERT, self.TEST_TEMPLATE)
        self._on_key_release(None)

    def _insert_step(self) -> None:
        self.text.insert(tk.INSERT, self.STEP_TEMPLATE)
        self._on_key_release(None)

    def _on_key_release(self, event: tk.Event | None) -> None:
        raw = self.text.get("1.0", tk.END)
        try:
            data = json.loads(raw)
            self.gui.plan = TestPlan.from_dict(data)
            self.gui.refresh_modules()
            self.status_var.set("JSON valid")
            self.text.config(background="white")
            self._update_suggestions()
        except Exception as exc:  # pragma: no cover - user input
            self.status_var.set(f"JSON error: {exc}")
            self.text.config(background="#ffecec")

    def _validate(self) -> bool:
        raw = self.text.get("1.0", tk.END)
        try:
            json.loads(raw)
        except Exception as exc:  # pragma: no cover - user input
            self.status_var.set(f"JSON error: {exc}")
            self.text.config(background="#ffecec")
            return False
        self.status_var.set("JSON valid")
        self.text.config(background="white")
        return True

    def _current_prefix(self) -> str:
        line_start = self.text.index("insert linestart")
        prior = self.text.get(line_start, "insert")
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)$", prior)
        return match.group(1) if match else ""

    def _update_suggestions(self) -> None:
        prefix = self._current_prefix()
        if prefix:
            matches = [k for k in self.KEYWORDS if k.startswith(prefix) and k != prefix]
            self.suggestions = matches
            if matches:
                self.status_var.set(
                    f"JSON valid - Suggestions: {', '.join(matches[:5])}"
                )
            else:
                self.status_var.set("JSON valid")
        else:
            self.suggestions = []
            self.status_var.set("JSON valid")

    def _autocomplete(self, event: tk.Event) -> str:
        if self.suggestions:
            prefix = self._current_prefix()
            suggestion = self.suggestions[0]
            if prefix:
                self.text.delete(f"insert -{len(prefix)}c", "insert")
            self.text.insert("insert", suggestion)
            self.suggestions = []
            self._update_suggestions()
            return "break"
        # default tab inserts 4 spaces
        self.text.insert("insert", "    ")
        return "break"

    def _handle_keypress(self, event: tk.Event) -> str | None:
        pairs = {"{": "}", "[": "]", '"': '"'}
        if event.char in pairs:
            self.text.insert("insert", event.char + pairs[event.char])
            self.text.mark_set("insert", "insert -1c")
            return "break"
        if event.keysym == "BackSpace":
            prev = self.text.get("insert -1c")
            nextc = self.text.get("insert")
            if (prev, nextc) in [("{", "}"), ("[", "]"), ('"', '"')]:
                self.text.delete("insert -1c", "insert +1c")
                return "break"
        return None

    def _run(self) -> None:
        raw = self.text.get("1.0", tk.END)
        try:
            data = json.loads(raw)
            self.gui.plan = TestPlan.from_dict(data)
            self.gui.refresh_modules()
        except Exception as exc:  # pragma: no cover - user input
            messagebox.showerror("JSON error", str(exc))
            return
        run_json_plan(
            data,
            ip=self.gui.ip_var.get(),
            rack=self.gui.rack_var.get(),
            slot=self.gui.slot_var.get(),
        )


class JsonEditDialog(tk.Toplevel):
    """Simple JSON editor for a portion of the plan."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        data: Dict[str, Any],
        on_save: Callable[[Dict[str, Any]], bool],
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(True, True)
        self.on_save = on_save

        self.text = tk.Text(self, width=60, height=20)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.insert("1.0", json.dumps(data, indent=2))

        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill=tk.X)
        ttk.Button(btn_frm, text="Save", command=self._save).pack(
            side=tk.LEFT, padx=5, pady=5
        )
        ttk.Button(btn_frm, text="Cancel", command=self.destroy).pack(
            side=tk.LEFT, padx=5, pady=5
        )

        self.grab_set()
        self.wait_visibility()
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self) -> None:
        raw = self.text.get("1.0", tk.END)
        try:
            data = json.loads(raw)
        except Exception as exc:  # pragma: no cover - user input
            messagebox.showerror("JSON error", str(exc))
            return
        if self.on_save(data):
            self.destroy()


class PLCConnection:
    """Wrapper around snap7 client."""

    def __init__(self) -> None:
        self.client = snap7.client.Client()
        self.connected = False

    def connect(self, ip: str, rack: int = 0, slot: int = 1) -> None:
        self.client.connect(ip, rack, slot)
        self.connected = True

    def disconnect(self) -> None:
        if self.connected:
            self.client.disconnect()
            self.connected = False

    def read(self, db: int, start: int, size: int) -> bytes:
        return self.client.db_read(db, start, size)

    def write(self, db: int, start: int, data: bytes) -> None:
        self.client.db_write(db, start, data)


class PLCTestGUI:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.plan = TestPlan()
        self.conn = PLCConnection()
        self.json_editor: PlanJsonEditor | None = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root.title("PLC Test Plan")

        # Connection frame
        conn_frm = ttk.LabelFrame(self.root, text="PLC Connection")
        conn_frm.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        conn_frm.columnconfigure(7, weight=1)

        ttk.Label(conn_frm, text="IP:").grid(row=0, column=0)
        self.ip_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(conn_frm, textvariable=self.ip_var, width=15).grid(row=0, column=1)

        ttk.Label(conn_frm, text="Rack:").grid(row=0, column=2)
        self.rack_var = tk.IntVar(value=0)
        ttk.Entry(conn_frm, textvariable=self.rack_var, width=5).grid(row=0, column=3)

        ttk.Label(conn_frm, text="Slot:").grid(row=0, column=4)
        self.slot_var = tk.IntVar(value=1)
        ttk.Entry(conn_frm, textvariable=self.slot_var, width=5).grid(row=0, column=5)

        ttk.Button(conn_frm, text="Connect", command=self.connect_plc).grid(row=0, column=6, padx=5)
        ttk.Button(conn_frm, text="Disconnect", command=self.disconnect_plc).grid(row=0, column=7, padx=5)

        # Module list
        module_frm = ttk.LabelFrame(self.root, text="Modules")
        module_frm.grid(row=1, column=0, padx=5, pady=5, sticky="ns")
        self.module_list = tk.Listbox(module_frm, height=10, exportselection=False)
        self.module_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.module_list.bind("<<ListboxSelect>>", lambda e: self.refresh_tests())
        self._disallow_space_select(self.module_list)
        ttk.Button(module_frm, text="Add", command=self.add_module).pack(fill=tk.X)
        ttk.Button(module_frm, text="Remove", command=self.remove_module).pack(fill=tk.X)
        ttk.Button(module_frm, text="Edit JSON", command=self.edit_module_json).pack(fill=tk.X)

        # Test list
        test_frm = ttk.LabelFrame(self.root, text="Tests")
        test_frm.grid(row=1, column=1, padx=5, pady=5, sticky="ns")
        self.test_list = tk.Listbox(test_frm, height=10, exportselection=False)
        self.test_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.test_list.bind("<<ListboxSelect>>", lambda e: self.refresh_steps())
        self._disallow_space_select(self.test_list)
        ttk.Button(test_frm, text="Add", command=self.add_test).pack(fill=tk.X)
        ttk.Button(test_frm, text="Remove", command=self.remove_test).pack(fill=tk.X)
        ttk.Button(test_frm, text="Edit JSON", command=self.edit_test_json).pack(fill=tk.X)

        # Step list
        step_frm = ttk.LabelFrame(self.root, text="Steps")
        step_frm.grid(row=1, column=2, padx=5, pady=5, sticky="ns")
        self.step_list = tk.Listbox(
            step_frm, height=10, width=40, exportselection=False
        )
        self.step_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._disallow_space_select(self.step_list)
        ttk.Button(step_frm, text="Add", command=self.add_step).pack(fill=tk.X)
        ttk.Button(step_frm, text="Edit", command=self.edit_step).pack(fill=tk.X)
        ttk.Button(step_frm, text="Remove", command=self.remove_step).pack(fill=tk.X)
        ttk.Button(step_frm, text="Edit JSON", command=self.edit_step_json).pack(fill=tk.X)

        # Run frame
        run_frm = ttk.LabelFrame(self.root, text="Run")
        run_frm.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        ttk.Button(run_frm, text="Run Plan", command=self.run_plan).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Run Selected Test", command=self.run_selected_test).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Load Plan", command=self.load_plan).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Save Plan", command=self.save_plan).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="JSON Editor", command=self.open_json_editor).pack(
            side=tk.LEFT, padx=5
        )

        self.log = tk.Text(self.root, height=10)
        self.log.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.root.rowconfigure(3, weight=1)

    def open_json_editor(self) -> None:
        """Open the built-in JSON plan editor."""
        if self.json_editor:
            self.json_editor.focus()
            return
        self.json_editor = PlanJsonEditor(self)

    def _sync_json_editor(self) -> None:
        """Update open JSON editor with the latest plan."""
        if self.json_editor:
            self.json_editor.update_from_plan()

    # ------------------------------------------------------------------ Helpers
    def _disallow_space_select(self, listbox: tk.Listbox) -> None:
        """Ignore clicks on empty space inside a Listbox.

        Tkinter's default Listbox behaviour allows clearing the current
        selection by clicking on the blank area below the last item. This
        method binds an event handler that prevents such clicks from
        changing the selection, ensuring users can only select actual
        items.
        """

        def handler(event: tk.Event) -> str | None:
            index = listbox.nearest(event.y)
            bbox = listbox.bbox(index)
            if not bbox or event.y > bbox[1] + bbox[3]:
                return "break"  # ignore clicks outside any item
            return None

        listbox.bind("<Button-1>", handler)

    def current_module(self) -> ModulePlan | None:
        idx = self.module_list.curselection()
        if not idx:
            return None
        return self.plan.modules[idx[0]]

    def current_test(self) -> TestCase | None:
        module = self.current_module()
        if not module:
            return None
        idx = self.test_list.curselection()
        if not idx:
            return None
        return module.tests[idx[0]]

    def refresh_modules(self) -> None:
        self.module_list.delete(0, tk.END)
        for m in self.plan.modules:
            self.module_list.insert(tk.END, m.name)
        self.refresh_tests()

    def refresh_tests(self) -> None:
        self.test_list.delete(0, tk.END)
        module = self.current_module()
        if module:
            for t in module.tests:
                self.test_list.insert(tk.END, t.name)
        self.refresh_steps()

    def refresh_steps(self) -> None:
        self.step_list.delete(0, tk.END)
        test = self.current_test()
        if test:
            for s in test.steps:
                start = (
                    ",".join(str(st) for st in s.start)
                    if isinstance(s.start, list)
                    else str(s.start)
                )
                dtype = (
                    ",".join(s.data_type)
                    if isinstance(s.data_type, list)
                    else s.data_type
                )

                def fmt(val: Any | List[Any] | None) -> str:
                    if val is None:
                        return ""
                    if isinstance(val, list):
                        return ",".join(str(v) for v in val)
                    return str(val)

                write = fmt(s.write)
                exp = fmt(s.expected)
                delay = f" D:{s.delay_ms}ms" if s.delay_ms else ""
                self.step_list.insert(
                    tk.END,
                    f"{s.description} | DB{s.db_number} [{start}] T:{dtype} W:{write} E:{exp}{delay}",
                )

    def log_msg(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    # ------------------------------------------------------------------ Add/remove
    def add_module(self) -> None:
        name = simpledialog.askstring("Module", "Module name:")
        if name:
            self.plan.modules.append(ModulePlan(name=name))
            self.refresh_modules()
            self._sync_json_editor()

    def remove_module(self) -> None:
        module = self.current_module()
        if not module:
            messagebox.showwarning("No selection", "Select a module to remove.")
            return
        self.plan.modules.remove(module)
        self.refresh_modules()
        self._sync_json_editor()

    def edit_module_json(self) -> None:
        module = self.current_module()
        idx = self.module_list.curselection()
        if not module or not idx:
            messagebox.showwarning("No selection", "Select a module to edit.")
            return
        data = asdict(module)

        def save(new_data: Dict[str, Any]) -> bool:
            try:
                tests = []
                for t in new_data.get("tests", []):
                    steps = [TestStep(**s) for s in t.get("steps", [])]
                    tests.append(TestCase(name=t["name"], steps=steps))
                new_module = ModulePlan(name=new_data.get("name", module.name), tests=tests)
            except Exception as exc:  # pragma: no cover - user input
                messagebox.showerror("JSON error", str(exc))
                return False
            self.plan.modules[idx[0]] = new_module
            self.refresh_modules()
            self.refresh_tests()
            self.refresh_steps()
            self._sync_json_editor()
            return True

        JsonEditDialog(self.root, "Edit Module JSON", data, save)

    def add_test(self) -> None:
        module = self.current_module()
        if not module:
            messagebox.showwarning("No module", "Select a module first.")
            return
        name = simpledialog.askstring("Test", "Test name:")
        if name:
            module.tests.append(TestCase(name=name))
            self.refresh_tests()
            self._sync_json_editor()

    def remove_test(self) -> None:
        module = self.current_module()
        test = self.current_test()
        if not (module and test):
            messagebox.showwarning("No selection", "Select a test to remove.")
            return
        module.tests.remove(test)
        self.refresh_tests()
        self._sync_json_editor()

    def edit_test_json(self) -> None:
        module = self.current_module()
        idx = self.test_list.curselection()
        if not module or not idx:
            messagebox.showwarning("No selection", "Select a test to edit.")
            return
        test = module.tests[idx[0]]
        data = asdict(test)

        def save(new_data: Dict[str, Any]) -> bool:
            try:
                steps = [TestStep(**s) for s in new_data.get("steps", [])]
                new_test = TestCase(name=new_data.get("name", test.name), steps=steps)
            except Exception as exc:  # pragma: no cover - user input
                messagebox.showerror("JSON error", str(exc))
                return False
            module.tests[idx[0]] = new_test
            self.refresh_tests()
            self.refresh_steps()
            self._sync_json_editor()
            return True

        JsonEditDialog(self.root, "Edit Test JSON", data, save)

    def add_step(self) -> None:
        test = self.current_test()
        if not test:
            messagebox.showwarning("No test", "Select a test first.")
            return
        editor = StepEditor(self.root)
        self.root.wait_window(editor)
        step = editor.result
        if step:
            test.steps.append(step)
            self.refresh_steps()
            self._sync_json_editor()
            self.suggest_next_step(step)

    def edit_step(self) -> None:
        test = self.current_test()
        idx = self.step_list.curselection()
        if not test or not idx:
            messagebox.showwarning("No selection", "Select a step to edit.")
            return
        step = test.steps[idx[0]]
        editor = StepEditor(self.root, step=step, title="Edit Step")
        self.root.wait_window(editor)
        new_step = editor.result
        if new_step:
            test.steps[idx[0]] = new_step
            self.refresh_steps()
            self._sync_json_editor()
            self.suggest_next_step(new_step)

    def remove_step(self) -> None:
        test = self.current_test()
        idx = self.step_list.curselection()
        if not (test and idx):
            messagebox.showwarning("No selection", "Select a step to remove.")
            return
        del test.steps[idx[0]]
        self.refresh_steps()
        self._sync_json_editor()

    def edit_step_json(self) -> None:
        test = self.current_test()
        idx = self.step_list.curselection()
        if not (test and idx):
            messagebox.showwarning("No selection", "Select a step to edit.")
            return
        step = test.steps[idx[0]]
        data = asdict(step)

        def save(new_data: Dict[str, Any]) -> bool:
            try:
                new_step = TestStep(**new_data)
            except Exception as exc:  # pragma: no cover - user input
                messagebox.showerror("JSON error", str(exc))
                return False
            test.steps[idx[0]] = new_step
            self.refresh_steps()
            self._sync_json_editor()
            self.suggest_next_step(new_step)
            return True

        JsonEditDialog(self.root, "Edit Step JSON", data, save)

    def suggest_next_step(self, step: TestStep) -> None:
        """Provide simple suggestions for likely next steps."""

        first_start = step.start[0] if isinstance(step.start, list) else step.start
        if step.write and not step.expected:
            self.log_msg(
                f"Suggestion: add a verification step for DB{step.db_number} start {first_start}."
            )
        elif step.expected and not step.write:
            self.log_msg("Suggestion: add a write step before verifying these bytes.")

    # ------------------------------------------------------------------ Load/Save
    def load_plan(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.plan = TestPlan.from_dict(data)
        self.refresh_modules()
        self._sync_json_editor()
        self.log_msg(f"Loaded plan from {path}")

    def save_plan(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.plan.to_dict(), f, indent=2)
        self.log_msg(f"Saved plan to {path}")

    # ------------------------------------------------------------------ Connection
    def connect_plc(self) -> None:
        try:
            self.conn.connect(self.ip_var.get(), self.rack_var.get(), self.slot_var.get())
            self.log_msg("Connected to PLC")
        except Exception as exc:  # pragma: no cover - network
            messagebox.showerror("Connection error", str(exc))

    def disconnect_plc(self) -> None:
        try:
            self.conn.disconnect()
            self.log_msg("Disconnected")
        except Exception as exc:  # pragma: no cover
            messagebox.showerror("Error", str(exc))

    # ------------------------------------------------------------------ Run tests
    def run_plan(self) -> None:
        for module in self.plan.modules:
            self.log_msg(f"Module: {module.name}")
            for test in module.tests:
                self._run_test(test)

    def run_selected_test(self) -> None:
        test = self.current_test()
        if not test:
            messagebox.showwarning("No test", "Select a test to run.")
            return
        self._run_test(test)

    def _run_test(self, test: TestCase) -> None:
        self.log_msg(f"  Test: {test.name}")
        success = True
        failures: List[str] = []
        for idx, step in enumerate(test.steps, start=1):
            self.log_msg(f"    Step {idx}: {step.description}")
            try:
                starts = step.start if isinstance(step.start, list) else [step.start]
                types = (
                    step.data_type
                    if isinstance(step.data_type, list)
                    else [step.data_type]
                )
                if len(types) == 1 and len(starts) > 1:
                    types = types * len(starts)
                writes = (
                    step.write if isinstance(step.write, list) else ([step.write] if step.write is not None else [])
                )
                expecteds = (
                    step.expected
                    if isinstance(step.expected, list)
                    else ([step.expected] if step.expected is not None else [])
                )

                if step.delay_ms:
                    self.log_msg(f"      Waiting {step.delay_ms} ms")
                    time.sleep(step.delay_ms / 1000.0)

                for sub_idx, start in enumerate(starts):
                    dtype = types[sub_idx]
                    w = writes[sub_idx] if sub_idx < len(writes) else None
                    e = expecteds[sub_idx] if sub_idx < len(expecteds) else None
                    if dtype == "BOOL":
                        byte_str, bit_str = str(start).split(".")
                        byte_idx, bit_idx = int(byte_str), int(bit_str)
                        if w is not None:
                            cur = bytearray(self.conn.read(step.db_number, byte_idx, 1))
                            set_bool(cur, 0, bit_idx, bool(w))
                            self.conn.write(step.db_number, byte_idx, bytes(cur))
                        if e is not None:
                            data = self.conn.read(step.db_number, byte_idx, 1)
                            val = get_bool(data, 0, bit_idx)
                            ok = val == bool(e)
                            self.log_msg(
                                f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}"
                            )
                            if not ok:
                                failures.append(
                                    f"step {idx} ({step.description}) at {start}: expected {e} got {val}"
                                )
                                success = False
                    elif dtype == "BYTE":
                        addr = int(start)
                        if w is not None:
                            self.conn.write(step.db_number, addr, bytes([int(w)]))
                        if e is not None:
                            data = self.conn.read(step.db_number, addr, 1)
                            val = data[0]
                            ok = val == int(e)
                            self.log_msg(
                                f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}"
                            )
                            if not ok:
                                failures.append(
                                    f"step {idx} ({step.description}) at {start}: expected {e} got {val}"
                                )
                                success = False
                    else:
                        size, set_func, get_func = TYPE_FUNCS[dtype]
                        addr = int(start)
                        if w is not None:
                            buf = bytearray(size)
                            set_func(buf, 0, w)
                            self.conn.write(step.db_number, addr, bytes(buf))
                        if e is not None:
                            data = self.conn.read(step.db_number, addr, size)
                            val = get_func(data, 0)
                            if dtype == "REAL":
                                ok = abs(val - float(e)) < 1e-6
                            else:
                                ok = val == e
                            self.log_msg(
                                f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}"
                            )
                            if not ok:
                                failures.append(
                                    f"step {idx} ({step.description}) at {start}: expected {e} got {val}"
                                )
                                success = False
            except Exception as exc:  # pragma: no cover - network
                self.log_msg(f"      Error: {exc}")
                failures.append(f"step {idx} ({step.description}): {exc}")
                success = False
        self.log_msg(f"  Result: {'PASSED' if success else 'FAILED'}")
        if failures:
            for reason in failures:
                self.log_msg(f"    Failure: {reason}")


def main() -> None:
    root = tk.Tk()
    app = PLCTestGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
