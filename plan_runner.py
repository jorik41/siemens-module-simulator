"""Execute PLC test plans programmatically without the GUI.

This module exposes helpers to run test plans defined either as
``plc_tester_gui.TestPlan`` instances or as JSON objects/files. The
behaviour mirrors the GUI runner but prints messages to the console,
allowing developers to define steps without using interactive dialogs.
"""

from __future__ import annotations

import json
import time
from typing import List, Union, Dict, Any

from plc_tester_gui import TestPlan, TestCase, PLCConnection, TYPE_FUNCS
from snap7.util import get_bool, set_bool


def run_plan(plan: TestPlan, ip: str = "127.0.0.1", rack: int = 0, slot: int = 1) -> None:
    """Run ``plan`` against the specified PLC."""
    conn = PLCConnection()
    conn.connect(ip, rack, slot)
    try:
        for module in plan.modules:
            print(f"Module: {module.name}")
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
    """Run a test plan described as JSON.

    ``data`` may be a path to a JSON file or a dictionary already loaded
    from JSON.
    """

    if isinstance(data, str):
        with open(data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    plan = TestPlan.from_dict(data)
    run_plan(plan, ip=ip, rack=rack, slot=slot)


def _run_test(conn: PLCConnection, test: TestCase) -> None:
    """Execute a single :class:`~plc_tester_gui.TestCase` using ``conn``."""

    print(f"  Test: {test.name}")
    success = True
    failures: List[str] = []
    for idx, step in enumerate(test.steps, start=1):
        print(f"    Step {idx}: {step.description}")
        try:
            starts = step.start if isinstance(step.start, list) else [step.start]
            types = step.data_type if isinstance(step.data_type, list) else [step.data_type]
            if len(types) == 1 and len(starts) > 1:
                types = types * len(starts)
            writes = step.write if isinstance(step.write, list) else ([step.write] if step.write is not None else [])
            expecteds = (
                step.expected if isinstance(step.expected, list) else ([step.expected] if step.expected is not None else [])
            )

            if step.delay_ms:
                print(f"      Waiting {step.delay_ms} ms")
                time.sleep(step.delay_ms / 1000.0)

            for sub_idx, start in enumerate(starts):
                dtype = types[sub_idx]
                w = writes[sub_idx] if sub_idx < len(writes) else None
                e = expecteds[sub_idx] if sub_idx < len(expecteds) else None
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
                        ok = val == bool(e)
                        print(f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}")
                        if not ok:
                            failures.append(
                                f"step {idx} ({step.description}) at {start}: expected {e} got {val}"
                            )
                            success = False
                elif dtype == "BYTE":
                    addr = int(start)
                    if w is not None:
                        conn.write(step.db_number, addr, bytes([int(w)]))
                    if e is not None:
                        data = conn.read(step.db_number, addr, 1)
                        val = data[0]
                        ok = val == int(e)
                        print(f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}")
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
                        conn.write(step.db_number, addr, bytes(buf))
                    if e is not None:
                        data = conn.read(step.db_number, addr, size)
                        val = get_func(data, 0)
                        if dtype == "REAL":
                            ok = abs(val - float(e)) < 1e-6
                        else:
                            ok = val == e
                        print(f"      Expect {e} got {val} -> {'OK' if ok else 'FAIL'}")
                        if not ok:
                            failures.append(
                                f"step {idx} ({step.description}) at {start}: expected {e} got {val}"
                            )
                            success = False
        except Exception as exc:  # pragma: no cover - network
            print(f"      Error: {exc}")
            failures.append(f"step {idx} ({step.description}): {exc}")
            success = False
    print(f"  Result: {'PASSED' if success else 'FAILED'}")
    for reason in failures:
        print(f"    Failure: {reason}")


__all__ = ["run_plan", "run_json_plan"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a PLC test plan from a JSON file",
    )
    parser.add_argument("plan", help="Path to JSON plan file")
    parser.add_argument("--ip", default="127.0.0.1", help="PLC IP address")
    parser.add_argument("--rack", type=int, default=0, help="PLC rack number")
    parser.add_argument("--slot", type=int, default=1, help="PLC slot number")
    args = parser.parse_args()

    run_json_plan(args.plan, ip=args.ip, rack=args.rack, slot=args.slot)

