"""
A simple GUI to create and run PLC test plans using Snap7.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import List

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

import snap7


@dataclass
class TestStep:
    """Single action within a test case."""
    description: str
    db_number: int
    start: int
    write: List[int] | None = None
    expected: List[int] | None = None


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
        self.module_list = tk.Listbox(module_frm, height=10)
        self.module_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.module_list.bind("<<ListboxSelect>>", lambda e: self.refresh_tests())
        ttk.Button(module_frm, text="Add", command=self.add_module).pack(fill=tk.X)
        ttk.Button(module_frm, text="Remove", command=self.remove_module).pack(fill=tk.X)

        # Test list
        test_frm = ttk.LabelFrame(self.root, text="Tests")
        test_frm.grid(row=1, column=1, padx=5, pady=5, sticky="ns")
        self.test_list = tk.Listbox(test_frm, height=10)
        self.test_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.test_list.bind("<<ListboxSelect>>", lambda e: self.refresh_steps())
        ttk.Button(test_frm, text="Add", command=self.add_test).pack(fill=tk.X)
        ttk.Button(test_frm, text="Remove", command=self.remove_test).pack(fill=tk.X)

        # Step list
        step_frm = ttk.LabelFrame(self.root, text="Steps")
        step_frm.grid(row=1, column=2, padx=5, pady=5, sticky="ns")
        self.step_list = tk.Listbox(step_frm, height=10, width=40)
        self.step_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        ttk.Button(step_frm, text="Add", command=self.add_step).pack(fill=tk.X)
        ttk.Button(step_frm, text="Remove", command=self.remove_step).pack(fill=tk.X)

        # Run frame
        run_frm = ttk.LabelFrame(self.root, text="Run")
        run_frm.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        ttk.Button(run_frm, text="Run Plan", command=self.run_plan).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Run Selected Test", command=self.run_selected_test).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Load Plan", command=self.load_plan).pack(side=tk.LEFT, padx=5)
        ttk.Button(run_frm, text="Save Plan", command=self.save_plan).pack(side=tk.LEFT, padx=5)

        self.log = tk.Text(self.root, height=10)
        self.log.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.root.rowconfigure(3, weight=1)

    # ------------------------------------------------------------------ Helpers
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
                write = ",".join(str(b) for b in s.write or [])
                exp = ",".join(str(b) for b in s.expected or [])
                self.step_list.insert(tk.END, f"{s.description} | DB{s.db_number} [{s.start}] W:{write} E:{exp}")

    def log_msg(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    # ------------------------------------------------------------------ Add/remove
    def add_module(self) -> None:
        name = simpledialog.askstring("Module", "Module name:")
        if name:
            self.plan.modules.append(ModulePlan(name=name))
            self.refresh_modules()

    def remove_module(self) -> None:
        module = self.current_module()
        if module:
            self.plan.modules.remove(module)
            self.refresh_modules()

    def add_test(self) -> None:
        module = self.current_module()
        if not module:
            return
        name = simpledialog.askstring("Test", "Test name:")
        if name:
            module.tests.append(TestCase(name=name))
            self.refresh_tests()

    def remove_test(self) -> None:
        module = self.current_module()
        test = self.current_test()
        if module and test:
            module.tests.remove(test)
            self.refresh_tests()

    def add_step(self) -> None:
        test = self.current_test()
        if not test:
            return
        desc = simpledialog.askstring("Step", "Description:")
        if desc is None:
            return
        db = simpledialog.askinteger("Step", "DB number:")
        if db is None:
            return
        start = simpledialog.askinteger("Step", "Start byte:")
        if start is None:
            return
        write_str = simpledialog.askstring("Step", "Bytes to write (comma separated):")
        exp_str = simpledialog.askstring("Step", "Expected bytes (comma separated):")
        write = [int(x) for x in write_str.split(",") if x.strip()] if write_str else None
        expected = [int(x) for x in exp_str.split(",") if x.strip()] if exp_str else None
        test.steps.append(TestStep(desc, db, start, write, expected))
        self.refresh_steps()

    def remove_step(self) -> None:
        test = self.current_test()
        idx = self.step_list.curselection()
        if test and idx:
            del test.steps[idx[0]]
            self.refresh_steps()

    # ------------------------------------------------------------------ Load/Save
    def load_plan(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.plan = TestPlan.from_dict(data)
        self.refresh_modules()
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
        if test:
            self._run_test(test)

    def _run_test(self, test: TestCase) -> None:
        self.log_msg(f"  Test: {test.name}")
        success = True
        for step in test.steps:
            self.log_msg(f"    {step.description}")
            try:
                if step.write:
                    self.conn.write(step.db_number, step.start, bytes(step.write))
                if step.expected:
                    data = self.conn.read(step.db_number, step.start, len(step.expected))
                    ok = list(data) == step.expected
                    self.log_msg(f"      Expect {step.expected} got {list(data)} -> {'OK' if ok else 'FAIL'}")
                    success &= ok
            except Exception as exc:  # pragma: no cover - network
                self.log_msg(f"      Error: {exc}")
                success = False
        self.log_msg(f"  Result: {'PASSED' if success else 'FAILED'}")


def main() -> None:
    root = tk.Tk()
    app = PLCTestGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
