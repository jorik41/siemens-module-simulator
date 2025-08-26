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

### Programmatic Test Plans

For automated scenarios you can define test plans as JSON and run them without
using the GUI dialogs. A minimal plan looks like:

```json
{
  "modules": [
    {
      "name": "Demo",
      "tests": [
        {
          "name": "Simple",
          "steps": [
            {
              "description": "Write and verify INT",
              "db_number": 1,
              "start": 0,
              "data_type": "INT",
              "write": 123,
              "expected": 123
            }
          ]
        }
      ]
    }
  ]
}
```

Save this to ``plan.json`` and execute it with:

```bash
python plan_runner.py plan.json --ip 127.0.0.1 --rack 0 --slot 1
```

See ``json_plan_example.json`` and ``run_json_example.py`` for a complete
example.

### In-GUI JSON Editor

The GUI includes a basic editor for these JSON plans. Use the **JSON Editor**
button in the *Run* frame to open it. The editor starts with a simple template
and expects a JSON object describing the plan. Press **Run** to execute the
plan against the connected PLC using the current connection settings.

### Step Input Tips

- Multiple start bytes can be entered separated by commas (e.g. `0,4,8`).
- Provide matching data types separated by commas (e.g. `INT,REAL`). Use `byte.bit` for BOOL addresses.
- Enter corresponding write or expected values separated by commas (e.g. `5,3.14`).
- An optional delay (milliseconds) can be specified to pause before executing the step's operations.

