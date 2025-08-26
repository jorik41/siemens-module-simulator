# Siemens Module Simulator

This repository contains a simple Python GUI application for creating and executing test plans against a Siemens PLC using the Snap7 library.

## Features

- Define modules, tests, and individual steps in a friendly GUI
- Write to and read from PLC data blocks
- Expect specific values and verify them step-by-step
- Execute simple delays between actions to build timer-based sequences
- Write and read multiple address/value pairs within a single step
- Support common Siemens data types (BOOL, BYTE, WORD, DWORD, INT, DINT, REAL)
- Save and load test plans as JSON files
- Integrated step editor with validation and smart suggestions for next actions
- Edit existing steps through a dedicated editor
- Detailed failure log identifying which step failed and why
- Built-in JSON editor with live syntax checking, auto-completion, and templates

## Usage

1. Install dependencies:
   ```bash
   pip install python-snap7
   ```
2. Run the GUI:
   ```bash
   python plc_tester_gui.py
   ```
3. Use the interface to create modules, add tests and steps, and run them against the connected PLC. Results appear in the log area.

### JSON Test Plans

Test plans can be represented as JSON and executed directly from the GUI. Use
the **JSON Editor** button in the *Run* frame to open a helper that validates
syntax as you type, suggests field names, supports Tab-based auto-completion,
and offers quick templates for modules, tests, and steps.
Modify the JSON as needed and press **Run** to execute it against the currently
connected PLC. Plans can also be saved to or loaded from disk using the standard
file dialogs.

### Step Input Tips

- Multiple start bytes can be entered separated by commas (e.g. `0,4,8`).
- Provide matching data types separated by commas (e.g. `INT,REAL`). Use `byte.bit` for BOOL addresses.
- Enter corresponding write or expected values separated by commas (e.g. `5,3.14`).
- An optional delay (milliseconds) can be specified to pause before executing the step's operations.

