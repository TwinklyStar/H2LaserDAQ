# H2LaserDAQ

Data Acquisition (DAQ) system for H2 laser experiments. Captures waveform data from PicoScope digitizers (PS3000A and PS2000 series), stores it in ROOT and CSV formats, and provides a real-time matplotlib GUI for signal monitoring.

**Monitored signals:** 355 nm, 212 nm, 820 nm laser via photodiodes, 122 nm laser via two VUV-compatible photodiode, and an NO cell detector.

**Developer:** Meng Lyu @ Dec. 2025

---

## Table of Contents

1. [Hardware Requirements](#hardware-requirements)
2. [Software Dependencies](#software-dependencies)
3. [Installation](#installation)
4. [Repository Structure](#repository-structure)
5. [Running the Applications](#running-the-applications)
6. [Configuration](#configuration)
7. [Data Output](#data-output)
8. [Architecture Overview](#architecture-overview)
9. [Viewing Historical Data](#viewing-historical-data)
10. [Troubleshooting](#troubleshooting)

---

## Hardware Requirements

| Device | Model | Role |
|--------|-------|------|
| PicoScope 3405D | `3405D` | Primary digitizer — 355/212/820 nm laser channels |
| PicoScope 2204A | `2204A` | Secondary digitizer — NO cell detector and VUV photodiode|

Multiple PicoScope 2204A units can be connected simultaneously; the system matches each unit to its config entry by **serial number**.

---

## Software Dependencies

No `requirements.txt` is provided. Install the following manually:

| Package | Purpose |
|---------|---------|
| `picosdk` | PicoScope hardware SDK Python bindings |
| `numpy` | Vectorized ADC conversion and waveform processing |
| `pyqtgraph` | Real-time DAQ monitor GUI |
| `PyQt5` | Qt backend for pyqtgraph |
| `uproot` | CERN ROOT file I/O (write) |
| `awkward` | Variable-length array support for uproot |
| `pandas` | CSV reading in the history viewer |
| `matplotlib` | History viewer plots only |

```bash
pip install picosdk numpy pyqtgraph PyQt5 uproot awkward pandas matplotlib
```

The PicoScope SDK also requires the native PicoSDK drivers to be installed on the host machine. Download from [Pico Technology](https://www.picotech.com/downloads).

---

## Installation

```bash
git clone https://github.com/TwinklyStar/H2LaserDAQ.git
cd H2LaserDAQ
```

### Python Environment (x86 required)

The PicoScope SDK requires an **x86 Python environment** (the native PicoSDK libraries are 32-bit/x86).

Create the output directories before first run:

```bash
mkdir -p data/root data/csv
```

No build step is required. All scripts run directly with Python 3.

---

## Repository Structure

```
H2LaserDAQ/
├── runH2LaserDAQ.py        # Main DAQ entry point (continuous monitoring + GUI)
├── runH2PD.py              # H2 photodiode snapshot mode
├── runLaserRoomPD.py       # Laser room photodiode monitoring
├── ps3000Snapshot.py       # PS3000 snapshot test/demo
├── runHistoryViewer.py     # Offline historical CSV data viewer
│
├── src/                    # Library package
│   ├── H2LaserDAQManager.py    # Thread coordinator: spawns and joins digitizer threads
│   ├── H2LaserDigitizer.py     # Core worker thread — one instance per PicoScope device
│   ├── H2LaserMonitorApp.py    # Real-time matplotlib GUI
│   ├── picoDAQAssistant.py     # Utility: RootManager, NumpyRingQueue, ADC converters
│   ├── H2Exceptions.py         # Custom exception: DigitizerInitError
│   └── utility.py              # Logging helper
│
├── config/                 # Configuration package
│   ├── config.py               # Default config: DET10A2 (PS3405D) + NOCell (PS2204A)
│   ├── config_H2PD.py          # Config for H2 photodiode snapshot run
│   ├── config_LaserRoomPD.py   # Config for laser room PD monitoring
│   ├── config_ps3000Snapshot.py # Config for PS3000 snapshot test
│   └── config_history.py       # Config for history viewer
│
├── test/                   # Hardware-free virtual tests
│   ├── VirtualDigitizer.py         # Drop-in mock: generates synthetic waveforms at 25 Hz
│   ├── config_virtual_continuous.py
│   ├── config_virtual_snapshot.py
│   ├── runVirtualContinuous.py     # Virtual continuous-mode test with full GUI
│   └── runVirtualSnapshot.py       # Virtual snapshot-mode test with full GUI
│
└── data/
    ├── root/               # ROOT files (daily, up to 10,000 triggers/file)
    └── csv/                # CSV files (daily, one row per 100-trigger aggregate)
```

---

## Running the Applications

### Primary DAQ (continuous monitoring with real-time GUI)

```bash
python3 runH2LaserDAQ.py
```

Reads `config/config.py` (`DIGITIZER_CONFIGS`). Starts one acquisition thread per configured digitizer and opens two matplotlib windows:

- **Signal monitor** — time-series of integrated peak area per channel (mV×ns)
- **Waveform monitor** — averaged raw waveform per channel (mV vs. ns)

**Stop:** close either GUI window, or press `Ctrl+C` in the terminal. All threads shut down cleanly.

---

### H2 Photodiode Snapshot

```bash
python3 runH2PD.py
```

Uses `config_H2PD.py`. Runs in **snapshot** mode: averages waveforms over a configurable number of triggers (`refresh_trigger_cnt`) and displays the result.

---

### Laser Room Photodiode Monitoring

```bash
python3 runLaserRoomPD.py
```

Uses `config_LaserRoomPD.py`. Same snapshot mode as above, targeted at the laser room PD.

---

### PS3000 Snapshot Test

```bash
python3 ps3000Snapshot.py
```

Uses `config_ps3000Snapshot.py`. Useful for verifying PS3405D hardware connectivity and sampling settings before a full DAQ run.

---

### Historical Data Viewer

```bash
python3 runHistoryViewer.py
```

Reads from `config_history.py`. Plots a selected channel from CSV files over a date range. Configure before running — see [Viewing Historical Data](#viewing-historical-data).

---

### Virtual Tests (no hardware required)

The `test/` folder contains two programs that exercise the full DAQ pipeline — ROOT write, CSV write, and real-time GUI — without a connected PicoScope. A synthetic **500 mV / 1 µs square pulse** is generated at **25 Hz** in software.

**Continuous mode:**

```bash
python3 test/runVirtualContinuous.py
```

Opens the same two-window `H2MonitorApp` GUI as the real DAQ. Data is aggregated over 100 triggers (~4 s) and written to `data/csv/` and `data/root/`. Integrated area per channel should read approximately **500 mV × 1000 ns = 5 × 10⁵ mV·ns**.

**Snapshot mode:**

```bash
python3 test/runVirtualSnapshot.py
```

Averages 100 waveforms per refresh and displays the averaged pulse shape plus peak-area statistics in a single matplotlib window. Data is written to `data/root/` only.

Both tests must be run from the **project root directory** and require the x86 virtualenv to be active (for `uproot`/`awkward`).

---

## Configuration

All DAQ programs read a `DIGITIZER_CONFIGS` dictionary from their respective config file. Each key is a device name; the value is a settings dict.

### Full Parameter Reference

```python
DIGITIZER_CONFIGS = {
    "DeviceName": {
        # --- Acquisition mode ---
        "run_mode": "continuous",   # "continuous" or "snapshot"

        # Snapshot-only parameters:
        "snapshot_channel": "A",    # Channel used for peak area in snapshot mode
        "refresh_trigger_cnt": 100, # Number of triggers to average before updating GUI

        # --- Hardware identification ---
        "model": "3405D",           # "3405D" (PS3000A series) or "2204A" (PS2000 series)
        "serial": "JY926/0005",     # PicoScope unit serial number (must match hardware)

        # --- Channel setup ---
        "channels": ["A", "B"],     # Active channels to enable (e.g. ["A"], ["A","B","C"])
        "channel_name": ["355", "212"],  # Human-readable label per channel (same order)
        "voltage_range": {          # Input voltage range per channel
            "A": "2V",              # Options: "10mV","20mV","50mV","100mV","200mV","500mV",
            "B": "10V"              #          "1V","2V","5V","10V","20V" (model-dependent)
        },
        "offset": {"A": 0, "B": 0}, # Analog offset in Volts (PS3000A only)

        # --- Timebase / sampling ---
        "timebase": 1252,           # See timebase guide below
        "sample_number": 1000,      # Samples per waveform (points per trigger)
        "pre_trigger": 10,          # % of samples before trigger point (0–100)

        # --- Trigger ---
        "trigger_channel": "A",     # "A","B","C","D" or "Ext" (PS3000A only)
        "trigger_level": 200,       # Trigger threshold in mV
        "trigger_edge": "RISING",   # "RISING" or "FALLING"
        "trigger_delay": 0,         # Samples to wait after trigger before capturing (PS3000A)
        "auto_trigger": 0,          # Auto-trigger timeout in ms; 0 = wait indefinitely

        # --- Output ---
        "output_name": "det10a2",   # Prefix for output file names
        "data_path": "data",        # Root directory for data output
    }
}
```

### Timebase Guide

**PS3405D (PS3000A series):**

| Timebase value | Sample interval |
|---------------|----------------|
| 0 | 1 ns (1 channel only) |
| 1 | 2 ns (≤2 channels) |
| 2 | 4 ns |
| n > 2 | (n − 2) × 8 ns |

Example: `timebase = 1252` → (1252 − 2) × 8 ns = **10 000 ns = 10 µs** per sample.

**PS2204A (PS2000 series):**

| Timebase value | Sample interval |
|---------------|----------------|
| 0 | 10 ns (1 channel only) |
| 1 | 20 ns |
| 2 | 40 ns |
| n | 10 × 2^n ns |

---

### Creating a Custom Configuration

1. Copy an existing config file:
   ```bash
   cp config.py config_myexperiment.py
   ```
2. Edit `DIGITIZER_CONFIGS` with your device serial numbers, channels, and parameters.
3. Update the corresponding `run*.py` script to import from your new config file:
   ```python
   from config_myexperiment import DIGITIZER_CONFIGS
   ```

---

## Data Output

All output is written under `data_path` (default: `data/`).

### ROOT Files (`data/root/`)

- Written by `picoDAQAssistant.RootManager` using `uproot`.
- File naming: `<output_name>_<YYMMDD>_<NNNN>.root` (e.g. `det10a2_251218_0000.root`)
- A new file is created every **10,000 triggers** (≈ 400 s at ~25 Hz).
- Writes happen asynchronously via a 3-buffer scheme to avoid blocking acquisition.

**Tree structure (`rawWave`):**

| Branch | Type | Description |
|--------|------|-------------|
| `Run` | int32 | Run number (always 0 currently) |
| `WaveN` | int32 | Sequential waveform index within the file |
| `Year`, `Month`, `Day` | int16/int8 | Timestamp date |
| `Hour`, `Min`, `Sec` | int8 | Timestamp time |
| `ms` | int16 | Milliseconds |
| `nTime` | int32 | Number of time samples |
| `Time` | float32[N] | Time axis (ns) |
| `ChA`, `ChB`, ... | float32[N] | Waveform in mV per enabled channel |

### CSV Files (`data/csv/`)

- Written in **continuous mode** only.
- File naming: `<output_name>_<YYMMDD>.csv` (e.g. `det10a2_251218.csv`)
- One file per day; rows are appended when the day rolls over.
- Each row represents an aggregate of **100 triggers** (~4 s of data).

**CSV columns:**

```
timestamp, <channel_name_1>, <channel_name_2>, ...
```

- `timestamp`: Unix timestamp (float, seconds)
- Channel columns: integrated peak area in **mV×ns** (sum of mV × sample interval, averaged over 100 triggers)

---

## Architecture Overview

```
runH2LaserDAQ.py
    └── H2LaserDAQManager       # Spawns and joins worker threads
            ├── H2LaserDigitizer (one thread per PicoScope)
            │       ├── picosdk ctypes API  →  hardware capture
            │       ├── picoDAQAssistant.RootManager  →  async ROOT writes
            │       └── CSV writes + queue.put()  →  GUI updates
            └── H2MonitorApp (GUI — main thread)
                    └── queue.get()  →  matplotlib real-time plots
```

**Threading model:**
- `H2LaserDAQManager` creates a shared `threading.Event` (stop signal) and a `queue.Queue` (data channel to GUI).
- Each `H2LaserDigitizer` runs as a daemon thread. On each trigger it captures a waveform block, converts ADC counts to mV, writes to ROOT, and (every 100 triggers in continuous mode) writes to CSV and pushes an update dict to the queue.
- `H2MonitorApp` runs on the main thread. It polls the queue at 10 Hz and redraws both figures.
- Ctrl+C or closing the GUI window sets the stop event, which causes all digitizer threads to exit their loops and call `close()` to stop and disconnect the hardware.

---

## Viewing Historical Data

Edit `config_history.py` to specify what to plot:

```python
HISTORY_CONFIG = {
    "run_name": "det10a2",          # Output name prefix used during data taking
    "channel_name": "355",          # Column name in the CSV to plot
    "data_path": "data/csv/",       # Path to the CSV directory
    "start_time": "2025-12-18 14:39:00",   # Local time (naive datetime)
    "end_time":   "2025-12-22 09:00:00",
}
```

Then run:

```bash
python3 runHistoryViewer.py
```

The viewer loads all daily CSV files in the date range, filters by the time window, and plots the selected channel as integrated area vs. time (displayed in JST).

---

## Troubleshooting

### `DigitizerInitError: Specified digitizer <model> <serial> not found`

- Check that the PicoScope is connected and powered on.
- Verify the serial number in the config matches what is printed on the unit.
- PS2204A: if multiple units are connected, all are opened and closed one by one until the matching serial is found. Ensure no other process has the device open.
- PS3405D: if the unit is on USB bus power only (no external supply), the SDK returns power status code 282; the code handles this automatically.

### `DigitizerInitError: Fail to set trigger`

- The trigger channel must be in the `channels` list (or `"Ext"` for external trigger on PS3405D).
- The trigger level must be within the configured voltage range of that channel.

### GUI does not update / appears frozen

- Data updates are pushed to the GUI every 100 triggers. If the trigger rate is low (or `auto_trigger = 0` and no signal is present), the GUI will not update until triggers are received.
- Set `auto_trigger` to a non-zero value (e.g. `1000` ms) to receive periodic auto-triggers regardless of signal.

### ROOT file write errors

- Ensure `data/root/` exists before starting the DAQ.
- `uproot` and `awkward` must be installed. Check with `python3 -c "import uproot, awkward"`.

### High CPU usage from GUI

- The GUI redraws at up to 10 Hz. On systems with slow rendering, reduce the sleep interval in `H2LaserMonitorApp.py:124` (`time.sleep(0.1)`).
