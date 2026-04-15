# H2LaserDAQ

Data Acquisition (DAQ) system for H2 laser experiments. Captures waveform data from PicoScope digitizers (PS3000A and PS2000 series), stores it in ROOT and CSV formats, and provides a real-time pyqtgraph GUI for signal monitoring.

**Monitored signals:** 355 nm, 212 nm, 820 nm laser lines via photodiodes, 122 nm VUV laser via VUV-compatible photodiodes, and an NO cell detector.

**Developer:** Meng Lyu, University of Tokyo, 2025–2026

---

## Table of Contents

1. [Hardware Requirements](#hardware-requirements)
2. [Software Dependencies](#software-dependencies)
3. [Installation](#installation)
4. [Repository Structure](#repository-structure)
5. [Running the Program](#running-the-program)
6. [Configuration](#configuration)
7. [GUI Reference](#gui-reference)
8. [Data Output](#data-output)
9. [Architecture Overview](#architecture-overview)
10. [Virtual Tests (no hardware)](#virtual-tests-no-hardware)
11. [Troubleshooting](#troubleshooting)

---

## Hardware Requirements

| Device | Model | Role |
|--------|-------|------|
| PicoScope 3405D | `3405D` | Primary digitizer — 355/212/820 nm laser channels |
| PicoScope 2204A | `2204A` | Secondary digitizer — NO cell detector and VUV photodiodes |

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

The PicoScope SDK also requires the native PicoSDK drivers installed on the host machine. Download from [Pico Technology](https://www.picotech.com/downloads).

---

## Installation

```bash
git clone https://github.com/TwinklyStar/H2LaserDAQ.git
cd H2LaserDAQ
```

### Python Environment (x86 required)

The PicoScope SDK requires an **x86 Python environment** (the native PicoSDK libraries are x86).

Create the output directories before the first run:

```bash
mkdir -p data/root data/csv data/snapshots
```

No build step is required. All scripts run directly with Python 3.

---

## Repository Structure

```
H2LaserDAQ/
│
├── runH2LaserDAQ.py        # ★ Unified entry point — interactive TUI launcher
│
├── runners/                # Run-mode implementations (called by the launcher)
│   ├── run_continuous.py       # Continuous DAQ — multi-digitizer, trend + waveform GUI
│   ├── run_snapshot.py         # Snapshot monitor — averaged waveform + peak-area stats
│   └── run_history_viewer.py   # Offline history viewer — plots CSV data over a date range
│
├── src/                    # Library package
│   ├── H2LaserDAQManager.py    # Thread coordinator: spawns and joins digitizer threads
│   ├── H2LaserDigitizer.py     # Core worker thread — one instance per PicoScope device
│   ├── H2LaserMonitorApp.py    # Real-time pyqtgraph GUI (monitor + snapshot windows)
│   ├── picoDAQAssistant.py     # Utilities: RootManager, ADC converters, ring buffer
│   ├── H2Exceptions.py         # Custom exception: DigitizerInitError
│   ├── banner.py               # Terminal banner / footer printer
│   └── utility.py              # Logging helper
│
├── config/                 # Configuration package — auto-discovered by the launcher
│   ├── config.py               # H2 Laser Room DAQ  (continuous, DET10A2 + NOCell)
│   ├── config_H2PD.py          # H2 VUV Photodiode  (snapshot)
│   ├── config_LaserRoomPD.py   # Laser Room VUV Photodiode  (snapshot)
│   ├── config_ps3000Snapshot.py # PS3000 Snapshot Test  (snapshot)
│   ├── config_history.py       # History viewer — NO Cell Dec 2025
│   └── config_history_bk.py    # History viewer — NO Cell first run Dec 2025
│
├── test/                   # Hardware-free virtual tests
│   ├── VirtualDigitizer.py         # Drop-in mock: synthetic waveforms at 25 Hz
│   ├── config_virtual_continuous.py
│   ├── config_virtual_snapshot.py
│   ├── runVirtualContinuous.py     # Virtual continuous-mode test
│   └── runVirtualSnapshot.py       # Virtual snapshot-mode test
│
└── data/
    ├── root/               # ROOT files (daily, up to 10 000 triggers/file)
    ├── csv/                # CSV files (continuous mode, daily, one row per 100 triggers)
    └── snapshots/          # Manually saved waveform snapshots from the snapshot GUI
```

---

## Running the Program

There is a single entry point for all run modes:

```bash
python3 runH2LaserDAQ.py
```

An interactive terminal menu appears. Navigate with the **arrow keys** and press **Enter** to confirm. Press **q** to quit.

### Level 1 — Select a run mode

```
    Select a run mode:

  ❯  Continuous DAQ
     Snapshot Monitor
     History Viewer
     ─────────────────
     Quit
```

### Level 2 — Select a config file

After choosing a mode, the launcher scans `config/` for all matching config files and lists them by their `CONFIG_TITLE`:

```
    Snapshot Monitor  →  Select a config:

  ❯  H2 VUV Photodiode             config_H2PD.py
     Laser Room VUV Photodiode     config_LaserRoomPD.py
     PS3000 Snapshot Test          config_ps3000Snapshot.py
     ─────────────────────────────────────────────────────
     ← Back
```

The launcher **automatically** reads every `*.py` file in `config/`, determines its mode from the `run_mode` field (or from `HISTORY_CONFIG`), and routes it to the correct runner. Adding a new config file requires no changes to any other file.

### Mode routing rules

| Config exports | `run_mode` value | Appears under |
|---|---|---|
| `DIGITIZER_CONFIGS` | `"continuous"` | Continuous DAQ |
| `DIGITIZER_CONFIGS` | `"snapshot"` | Snapshot Monitor |
| `HISTORY_CONFIG` | *(n/a)* | History Viewer |

### Stop / exit

- Close the GUI window, or press **Ctrl+C** in the terminal — all threads shut down cleanly.
- The launcher exits after one run. Re-run the script to start again.

---

## Configuration

### Digitizer config files (`DIGITIZER_CONFIGS`)

Each digitizer config file must export two module-level names:

```python
CONFIG_TITLE = "My Experiment"   # shown in the launcher menu

DIGITIZER_CONFIGS = {
    "DeviceName": {
        ...
    }
}
```

`CONFIG_TITLE` is the human-readable label shown in the interactive menu. It is **required** for the launcher to display the config correctly (the module path is used as a fallback if omitted).

#### Full parameter reference

```python
DIGITIZER_CONFIGS = {
    "DeviceName": {

        # ── Acquisition mode ──────────────────────────────────────────────────
        "run_mode": "continuous",   # "continuous" or "snapshot"

        # Snapshot-only:
        "snapshot_channel": "A",    # Channel used for peak-area statistics
        "refresh_trigger_cnt": 100, # Triggers averaged before each GUI update

        # ── Hardware identification ───────────────────────────────────────────
        "model":  "3405D",          # "3405D" (PS3000A) or "2204A" (PS2000)
        "serial": "JY926/0005",     # Unit serial number — must match hardware

        # ── Channel setup ─────────────────────────────────────────────────────
        "channels":      ["A", "B"],          # Active channels to enable
        "channel_name":  ["355", "212"],       # Human-readable label per channel
        "voltage_range": {"A": "2V", "B": "10V"},  # Input range per channel
        # Options: "10mV","20mV","50mV","100mV","200mV","500mV",
        #          "1V","2V","5V","10V","20V"  (model-dependent)
        "offset": {"A": 0, "B": 0},           # Analog offset in V (PS3000A only)

        # ── Timebase / sampling ───────────────────────────────────────────────
        "timebase":      1252,    # See timebase guide below
        "sample_number": 1000,    # Samples per waveform
        "pre_trigger":   10,      # % of samples before the trigger point (0–100)

        # ── Trigger ───────────────────────────────────────────────────────────
        "trigger_channel": "A",   # "A","B","C","D" or "Ext" (PS3000A only)
        "trigger_level":   200,   # Threshold in mV
        "trigger_edge":    "RISING",  # "RISING" or "FALLING"
        "trigger_delay":   0,     # Samples to wait after trigger (PS3000A only)
        "auto_trigger":    0,     # Auto-trigger timeout in ms; 0 = wait indefinitely

        # ── Output ────────────────────────────────────────────────────────────
        "output_name": "det10a2", # Prefix for output file names
        "data_path":   "data",    # Root directory for data output
    }
}
```

#### Timebase guide

**PS3405D (PS3000A series):**

| Timebase | Sample interval |
|----------|----------------|
| 0 | 1 ns (1 channel only) |
| 1 | 2 ns (≤ 2 channels) |
| 2 | 4 ns |
| n > 2 | (n − 2) × 8 ns |

Example: `timebase = 52` → (52 − 2) × 8 = **400 ns/sample**.

**PS2204A (PS2000 series):**

| Timebase | Sample interval |
|----------|----------------|
| 0 | 10 ns (1 channel only) |
| 1 | 20 ns |
| 2 | 40 ns |
| n | 10 × 2ⁿ ns |

---

### History viewer config files (`HISTORY_CONFIG`)

```python
CONFIG_TITLE = "History — My Channel (date range)"

HISTORY_CONFIG = {
    "run_name":     "det10a2",              # Output name prefix used during data-taking
    "channel_name": "355",                  # CSV column to plot
    "data_path":    "data/csv/",            # Path to the CSV directory
    "start_time":   "2025-12-18 14:39:00",  # Start of plot window (local naive time)
    "end_time":     "2025-12-22 09:00:00",  # End of plot window
}
```

---

### Adding a new configuration

1. Copy an existing config file:
   ```bash
   cp config/config_H2PD.py config/config_myexperiment.py
   ```
2. Edit `CONFIG_TITLE`, the device parameters, and `run_mode` as needed.
3. Run `python3 runH2LaserDAQ.py` — the new config appears in the menu automatically.

No other files need to be modified.

---

## GUI Reference

Both run modes use a **dark-themed pyqtgraph GUI** (Catppuccin Mocha palette).

### Continuous DAQ window

Two side-by-side panels:

| Panel | Content |
|-------|---------|
| **Signal Trends** | Time-series of integrated peak area per channel (nV·s) vs. wall-clock time |
| **Live Waveforms** | Averaged raw waveform per channel (V vs. µs) |

Channels from different digitizers have **independent X-axis zoom** in the waveform panel (different time windows do not interfere).

### Snapshot Monitor window

A single waveform panel showing the averaged waveform for each configured channel, plus a statistics strip at the bottom.

#### Statistics strip buttons

| Button | Action |
|--------|--------|
| **Pause** | Freeze the display; incoming data is discarded. Press **Resume** to continue. |
| **Freeze** | Capture the current signal-channel waveform as a dashed reference line. Press **Clear** to remove it. |
| **Save** | Save the current waveform to `data/snapshots/snapshot_<device>_<YYYYMMDD>_<NNN>.csv`. If a frozen reference is active, it is included as a third column. |

The **Math** readout (yellow, right of Freeze) shows `live area − frozen area` in nV·s whenever a reference is active.

#### Waveform Y-axis controls

Each channel row has **+** / **−** buttons on the right side. These step through a fixed range list:

```
−5 V → −2 V → −1 V → −500 mV → −200 mV → −100 mV → −50 mV → −20 mV → −10 mV
→ +10 mV → +20 mV → +50 mV → +100 mV → +200 mV → +500 mV → +1 V → +2 V → +5 V
```

The sign determines polarity: a negative range sets the bulk of the Y axis below zero (for negative-polarity signals). A 10 % margin is always added on the opposite-polarity side.

The first waveform received automatically selects the best-fit range; subsequent button presses adjust from there.

#### Mouse controls (both windows)

| Action | Effect |
|--------|--------|
| Left-click drag | Rubber-band **rect zoom** |
| Right-click drag | **Pan** |
| Scroll wheel | Zoom on the axis under cursor |

---

## Data Output

All output is written under `data_path` (default: `data/`).

### ROOT files (`data/root/`)

- Written asynchronously by `picoDAQAssistant.RootManager` via `uproot`.
- Naming: `<output_name>_<YYMMDD>_<NNNN>.root` (e.g. `det10a2_251218_0000.root`)
- A new file is opened every **10 000 triggers** (~400 s at 25 Hz).

**Tree structure (`rawWave`):**

| Branch | Type | Description |
|--------|------|-------------|
| `Run` | int32 | Run number (always 0) |
| `WaveN` | int32 | Sequential waveform index within the file |
| `Year`, `Month`, `Day` | int16/int8 | Date |
| `Hour`, `Min`, `Sec` | int8 | Time |
| `ms` | int16 | Milliseconds |
| `nTime` | int32 | Number of time samples |
| `Time` | float32[N] | Time axis (ns) |
| `ChA`, `ChB`, … | float32[N] | Waveform in mV per enabled channel |

### CSV files (`data/csv/`) — continuous mode only

- Naming: `<output_name>_<YYMMDD>.csv` (e.g. `det10a2_251218.csv`)
- One file per day; rows appended on date rollover.
- Each row is an aggregate of **100 triggers** (~4 s of data at 25 Hz).

**Columns:**

```
timestamp, <channel_name_1>, <channel_name_2>, ...
```

- `timestamp` — Unix time (float, seconds)
- Channel columns — integrated peak area in **nV·s**

### Snapshot saves (`data/snapshots/`)

Created when the **Save** button is pressed in snapshot mode.

- Naming: `snapshot_<device>_<YYYYMMDD>_<NNN>.csv`
- Auto-incremented sequence number per day.

**File format:**

```
# H2LaserDAQ Snapshot
# Saved   : 2026-04-15  14:23:45
# Device  : H2PD
# Channel : A (Sig)
# Area (live)  : 1.2345e-3 ± 4.56e-5  nV·s  (N = 100 triggers)
# Area (frozen): 1.2000e-3  nV·s          ← only if Freeze was active
# Area (Math)  : +3.45e-5   nV·s          ← only if Freeze was active
#
time_s,live_V[,frozen_V]
-4.55e-07,1.23e-03,...
```

---

## Architecture Overview

```
runH2LaserDAQ.py  (interactive TUI launcher)
    │
    ├── discovers config/*.py automatically
    ├── presents 2-level arrow-key menu
    └── imports and calls runners.<mode>.main(config_dict)

runners/run_continuous.py          runners/run_snapshot.py
    └── H2LaserDAQManager              └── H2LaserDAQManager
            ├── H2LaserDigitizer               └── H2LaserDigitizer
            │   (one thread per device)            (one thread, snapshot mode)
            │   ├── hardware capture
            │   ├── RootManager → ROOT write
            │   └── queue.put() → GUI update
            └── H2MonitorApp                   └── H2SnapshotApp
                (continuous GUI)                   (snapshot GUI)
```

### Threading model

- `H2LaserDAQManager` creates a shared `threading.Event` (stop signal) and a `queue.Queue` (data channel to GUI).
- Each `H2LaserDigitizer` runs in its own thread. After each trigger it converts ADC → mV, writes to ROOT, and (in continuous mode) every 100 triggers writes to CSV and pushes an update to the queue.
- The GUI polls the queue at **10 Hz** and redraws plots.
- Ctrl+C or closing the GUI window sets the stop event, causing all digitizer threads to exit cleanly and disconnect hardware.

### Continuous mode — multi-digitizer notes

- Each digitizer thread counts its **own** 100 triggers independently. Two digitizers may push GUI updates at different times within the same ~4 s window.
- Channels from different digitizers may have **different time windows and sample rates**. The waveform panel X-axis is linked only within channels of the same digitizer; each digitizer group has its own independent zoom.

### Snapshot mode — trigger counting

The `refresh_trigger_cnt` parameter controls how many triggers are averaged before the GUI is updated. `area_avg` and `area_std` are computed over these triggers. The averaging resets after each GUI update.

---

## Virtual Tests (no hardware)

The `test/` directory contains two programs that exercise the full pipeline — ROOT write, CSV write, real-time GUI — without a connected PicoScope.

A synthetic pulse is generated at **25 Hz** with:
- **Amplitude** sampled from N(nominal, (5 % × nominal)²) each trigger
- **Width** sampled from N(nominal, (5 % × nominal)²) each trigger

This simulates realistic pulse-to-pulse variation and allows the snapshot statistics strip to show non-zero standard deviations.

Default pulse: **−700 mV amplitude**, **1000 ns width** (single channel: `VirtualDigitizer.PULSE_AMPLITUDE_MV` / `PULSE_WIDTH_NS`).

```bash
# From the project root:
python3 test/runVirtualContinuous.py
python3 test/runVirtualSnapshot.py
```

Both tests require the x86 virtualenv to be active (for `uproot`/`awkward`).

---

## Troubleshooting

### `DigitizerInitError: Specified digitizer <model> <serial> not found`

- Check the PicoScope is connected, powered on, and not open in another application.
- Verify the serial number in the config matches the label on the unit.
- PS3405D on USB bus power: power status code 282 is handled automatically.

### `DigitizerInitError: Fail to set trigger`

- The trigger channel must be in the `channels` list (or `"Ext"` on PS3405D).
- The trigger level must be within the configured voltage range of that channel.

### GUI does not update

- In continuous mode, updates arrive every 100 triggers. If the trigger rate is low (or `auto_trigger = 0` and no signal is present), the display will not refresh until triggers come in.
- Set `auto_trigger` to a non-zero value (e.g. `1000` ms) for periodic auto-triggers.

### Wrong mode error on launch

- The launcher filters configs by `run_mode` and only shows matching configs in the menu, so a mode mismatch cannot happen through normal use.
- If calling a runner directly (e.g. in scripts), a `ValueError` is raised with a descriptive message if the config `run_mode` does not match the runner.

### ROOT file write errors

- Ensure `data/root/` exists: `mkdir -p data/root`
- Verify `uproot` and `awkward` are installed: `python3 -c "import uproot, awkward"`

### `data/snapshots/` directory missing

- Create it before saving: `mkdir -p data/snapshots`
- Or simply click **Save** once — the directory is created automatically.
