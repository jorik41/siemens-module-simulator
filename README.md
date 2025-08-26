# Siemens Module Simulator

This repository contains a simple Python GUI application for creating and executing test plans against a Siemens PLC using the Snap7 library.

## Features

- Define modules, tests, and individual steps in a friendly GUI
- Write to and read from PLC data blocks
- Expect specific values and verify them step-by-step
- Save and load test plans as JSON files
- Integrated step editor with validation and smart suggestions for next actions
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

