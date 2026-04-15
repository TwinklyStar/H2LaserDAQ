# H2LaserMonitorApp.py
# Real-time DAQ monitor built with pyqtgraph + PyQt5.
#
# Layout (single window):
#
#   ┌─ H2Laser DAQ Monitor ──────────────────────────────────────────────┐
#   │  ┌─ Signal Trends ──────────────────┐ ┌─ Live Waveforms ─────────┐ │
#   │  │  ch1 ─────────────────────────── │ │  ch1  ──/‾‾‾\──────────  │ │
#   │  │  ch2 ─────────────────────────── │ │  ch2  ──/‾‾‾\──────────  │ │
#   │  │  ...                             │ │  ...                     │ │
#   │  └──────────────────────────────────┘ └──────────────────────────┘ │
#   │  Last update: 12:34:56  | 355: 1.23e5 | 212: 4.56e4 | ...         │
#   └────────────────────────────────────────────────────────────────────┘
#
# Public interface (same as old matplotlib version):
#   H2MonitorApp(channels, update_queue)
#   H2MonitorApp.run()   — blocks until the window is closed

import math
import os
import queue
import signal
from collections import deque
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore

_SNAPSHOT_DIR = os.path.join("data", "snapshots")

# ---------------------------------------------------------------------------
# Colour scheme (Catppuccin Mocha dark palette)
# ---------------------------------------------------------------------------
_BG   = "#1e1e2e"   # window / plot background
_FG   = "#cdd6f4"   # default text
_SURF = "#313244"   # panel header background
_GRID = "#45475a"   # grid line colour

# Per-channel accent colours — cycled for more than 8 channels
_CH_COLOURS = [
    "#a6e3a1",  # green
    "#89b4fa",  # blue
    "#fab387",  # peach
    "#f38ba8",  # red
    "#cba6f7",  # mauve
    "#89dceb",  # sky
    "#f9e2af",  # yellow
    "#94e2d5",  # teal
]


def _colour(i: int) -> str:
    return _CH_COLOURS[i % len(_CH_COLOURS)]


# ---------------------------------------------------------------------------
# Vertical-range helpers
# ---------------------------------------------------------------------------

# Signed range list.  Positive value → signal points up; negative → down.
# Stepping + increases the index; stepping − decreases it.
# Example sequence through zero: ... −20 mV → −10 mV → +10 mV → +20 mV → ...
_SIGNED_RANGES = [
    -5.0, -2.0, -1.0, -0.5, -0.2, -0.1, -0.05, -0.02, -0.01,
     0.01, 0.02, 0.05,  0.1,  0.2,  0.5,   1.0,   2.0,   5.0,
]
_V_RANGES = [0.010, 0.020, 0.050, 0.100, 0.200, 0.500, 1.0, 2.0, 5.0]


def _yrange_from_signed(rv: float):
    """
    Convert a signed range value to (ymin, ymax) in volts.
    A 10 % margin is always added on the opposite-polarity side so that
    baseline noise and undershoot/overshoot remain visible.
      rv > 0  →  ( −rv×0.10,  rv )   e.g. 0.5 V → [−50 mV, 500 mV]
      rv < 0  →  (  rv,       −rv×0.10 )
    """
    margin = abs(rv) * 0.10
    return (-margin, rv) if rv > 0 else (rv, margin)


def _pick_range_idx(wfm_v: np.ndarray) -> int:
    """Return the index into _SIGNED_RANGES that best fits the waveform."""
    peak = float(np.max(np.abs(wfm_v)))
    if peak == 0.0:
        return _SIGNED_RANGES.index(0.01)   # smallest positive range
    r = _V_RANGES[-1]
    for candidate in _V_RANGES:
        if candidate >= peak:
            r = candidate
            break
    # Polarity: whichever extreme is larger wins
    signed_r = r if abs(float(np.max(wfm_v))) >= abs(float(np.min(wfm_v))) else -r
    return _SIGNED_RANGES.index(signed_r)


def _fmt_range(rv: float) -> str:
    """Human-readable label for a signed range value, e.g. '−100 mV', '1 V'."""
    sign = "−" if rv < 0 else ""
    r    = abs(rv)
    if r < 1.0:
        return f"{sign}{int(round(r * 1000))} mV"
    return f"{sign}{int(r)} V"


# ---------------------------------------------------------------------------
# Custom ViewBox: left-click = rect zoom, right-click drag = pan
# ---------------------------------------------------------------------------

class _ZoomPanViewBox(pg.ViewBox):
    """
    ViewBox with scientific-instrument mouse bindings:
      • Left-click drag  → rubber-band rect zoom
      • Right-click drag → pan
      • Scroll wheel     → zoom on the axis under cursor
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseMode(pg.ViewBox.RectMode)

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            # Replicate pyqtgraph's internal pan logic (same as left-click in
            # PanMode) so the right-click drag pans the view.
            dif  = pg.Point(ev.screenPos() - ev.lastScreenPos())
            mask = np.array(self.state["mouseEnabled"], dtype=float)
            tr   = pg.functions.invertQTransform(self.childGroup.transform())
            tr   = tr.map(dif * mask) - tr.map(pg.Point(0, 0))
            x    = -tr.x() if mask[0] else None
            y    = -tr.y() if mask[1] else None
            self._resetTarget()
            if x is not None or y is not None:
                self.translateBy(x=x, y=y)
            self.sigRangeChangedManually.emit(self.state["mouseEnabled"])
        else:
            super().mouseDragEvent(ev, axis)


def _setup_sigint(window: QtWidgets.QMainWindow):
    """
    Allow Ctrl+C to close a Qt window cleanly.

    Qt's event loop normally swallows SIGINT.  The fix is two parts:
      1. Install a Python signal handler that calls window.close().
      2. Run a no-op QTimer at 200 ms so Python's signal-checking code
         gets called regularly even while Qt is blocking in its event loop.
    """
    signal.signal(signal.SIGINT, lambda *_: window.close())
    timer = QtCore.QTimer(window)
    timer.timeout.connect(lambda: None)   # wake Python to check signals
    timer.start(200)


def _apply_dark_style(window: QtWidgets.QMainWindow):
    """Apply the shared dark stylesheet to any monitor window."""
    window.setStyleSheet(f"""
        QMainWindow, QWidget  {{ background: {_BG}; color: {_FG};
                                font-family: Menlo, Consolas, monospace;
                                font-size: 12px; }}
        QLabel#panelTitle     {{ font-size: 13px; font-weight: bold;
                                padding: 4px 8px;
                                background: {_SURF};
                                border-radius: 4px; }}
        QLabel#statsLabel     {{ font-size: 12px; padding: 2px 10px;
                                background: {_SURF};
                                border-radius: 4px; }}
        QStatusBar            {{ background: {_SURF};
                                border-top: 1px solid {_GRID}; }}
        QSplitter::handle     {{ background: {_GRID}; width: 3px; }}
        QFrame#statsSep       {{ color: {_GRID}; }}
        QPushButton           {{ background: {_SURF}; color: {_FG};
                                border: 1px solid {_GRID}; border-radius: 4px;
                                font-size: 15px; font-weight: bold; padding: 0px; }}
        QPushButton:hover     {{ background: {_GRID}; }}
        QPushButton:pressed   {{ background: #585b70; }}
    """)


# ---------------------------------------------------------------------------
# Public entry point — same interface as the old matplotlib H2MonitorApp
# ---------------------------------------------------------------------------

class H2MonitorApp:
    """
    Real-time DAQ monitor.

    Parameters
    ----------
    channels : list[str]
        Ordered list of channel names expected in queue items.
    update_queue : queue.Queue
        Queue fed by H2LaserDigitizer threads.  Each item is a dict::

            {
                "channel_name": str,
                "timestamp":    float,   # Unix time
                "value":        float,   # integrated area [nV·s]
                "wfm_t":        array,   # time axis [ns]
                "wfm":          array,   # voltage [mV]
            }
    """

    def __init__(self, channels: list, update_queue: queue.Queue,
                 channel_groups: list = None):
        pg.setConfigOption("background", _BG)
        pg.setConfigOption("foreground", _FG)
        pg.setConfigOption("antialias", True)
        self._app = pg.mkQApp("H2Laser DAQ Monitor")
        self._win = _MonitorWindow(channels, update_queue, channel_groups)
        self._win.show()

    def run(self):
        """Start the Qt event loop; returns only when the window is closed."""
        try:
            pg.exec()
        except KeyboardInterrupt:
            self._win.close()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class _MonitorWindow(QtWidgets.QMainWindow):

    _BUFFER   = 4000   # circular buffer length (points) per channel
    _POLL_MS  = 100    # queue-poll interval → 10 Hz refresh

    def __init__(self, channels: list, update_queue: queue.Queue,
                 channel_groups: list = None):
        super().__init__()
        self.channels     = channels
        self.update_queue = update_queue

        # channel_groups: list of channel-name lists, one per digitizer.
        # Channels in the same group share an X axis in the waveform panel.
        # If None, all channels are treated as one group.
        if channel_groups is None:
            channel_groups = [channels]
        # Build lookup: channel name → group index
        self._group_of: dict = {}
        for g_idx, grp in enumerate(channel_groups):
            for ch in grp:
                self._group_of[ch] = g_idx
        # Last displayed channel in each group (gets the time-axis label)
        self._wfm_group_tail: set = set()
        for grp in channel_groups:
            displayed = [ch for ch in grp if ch in channels]
            if displayed:
                self._wfm_group_tail.add(displayed[-1])

        self._ts  = {ch: deque(maxlen=self._BUFFER) for ch in channels}
        self._val = {ch: deque(maxlen=self._BUFFER) for ch in channels}

        self.setWindowTitle("H2Laser DAQ Monitor  (v3)")
        self.resize(1500, 900)
        self._apply_style()
        self._build_ui()
        _setup_sigint(self)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self._POLL_MS)

    # ── global style ────────────────────────────────────────────────────────

    def _apply_style(self):
        _apply_dark_style(self)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        vlay = QtWidgets.QVBoxLayout(root)
        vlay.setContentsMargins(8, 8, 8, 4)
        vlay.setSpacing(4)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(3)
        vlay.addWidget(splitter)

        trend_panel, self._trend_curves                  = self._make_trend_panel()
        wfm_panel,   self._wfm_curves, self._wfm_plots  = self._make_wfm_panel()
        splitter.addWidget(trend_panel)
        splitter.addWidget(wfm_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 600])

        self._build_statusbar()

    # ── trend panel ──────────────────────────────────────────────────────────

    def _make_trend_panel(self):
        panel, gw = self._make_panel("Signal Trends  (nV·s)")
        curves    = {}
        prev      = None
        n         = len(self.channels)

        for i, ch in enumerate(self.channels):
            col       = _colour(i)
            date_axis = pg.DateAxisItem(orientation="bottom")
            p = gw.addPlot(row=i, col=0, axisItems={"bottom": date_axis},
                           viewBox=_ZoomPanViewBox())
            p.setLabel("left", ch, units="nV·s", color=col, size="10pt")
            # Compound unit — disable SI prefix to prevent "knV·s", "MnV·s" etc.
            p.getAxis("left").enableAutoSIPrefix(False)
            p.showGrid(x=True, y=True, alpha=0.20)
            p.getAxis("left").setWidth(90)
            if i < n - 1:
                p.hideAxis("bottom")
            if prev is not None:
                p.setXLink(prev)
            curves[ch] = p.plot(pen=pg.mkPen(col, width=2))
            gw.ci.layout.setRowStretchFactor(i, 1)
            prev = p

        return panel, curves

    # ── waveform panel ───────────────────────────────────────────────────────

    def _make_wfm_panel(self):
        panel = QtWidgets.QWidget()
        vlay  = QtWidgets.QVBoxLayout(panel)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(2)

        title_lbl = QtWidgets.QLabel("Live Waveforms")
        title_lbl.setObjectName("panelTitle")
        vlay.addWidget(title_lbl)

        curves             = {}
        plots              = {}
        self._range_idx    = {}   # channel → index into _SIGNED_RANGES (None = not yet set)
        self._range_labels = {}   # channel → QLabel showing current range
        prev_per_group: dict = {}  # group_idx → last PlotItem (X-link anchor)

        for i, ch in enumerate(self.channels):
            col   = _colour(i)
            g_idx = self._group_of.get(ch, 0)
            prev  = prev_per_group.get(g_idx)

            # ── per-channel row ──────────────────────────────────────────────
            row     = QtWidgets.QWidget()
            row_lay = QtWidgets.QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(2)

            gw = pg.GraphicsLayoutWidget()
            gw.setBackground(_BG)
            p  = gw.addPlot(row=0, col=0, viewBox=_ZoomPanViewBox())
            p.setLabel("left", ch, units="V", color=col, size="10pt")
            p.showGrid(x=True, y=True, alpha=0.20)
            p.getAxis("left").setWidth(75)
            # Show the time axis only at the bottom of each digitizer group
            if ch in self._wfm_group_tail:
                p.setLabel("bottom", "Time", units="s")
            else:
                p.hideAxis("bottom")
            if prev is not None:
                p.setXLink(prev)

            # ── range-control buttons ────────────────────────────────────────
            btn_panel = QtWidgets.QWidget()
            btn_panel.setFixedWidth(52)
            btn_lay   = QtWidgets.QVBoxLayout(btn_panel)
            btn_lay.setContentsMargins(2, 4, 2, 4)
            btn_lay.setSpacing(2)

            btn_plus  = QtWidgets.QPushButton("+")
            btn_plus.setFixedSize(44, 26)
            btn_plus.setFocusPolicy(QtCore.Qt.NoFocus)

            range_lbl = QtWidgets.QLabel("—")
            range_lbl.setAlignment(QtCore.Qt.AlignCenter)
            range_lbl.setStyleSheet(f"color: {col}; font-size: 10px;")

            btn_minus = QtWidgets.QPushButton("−")
            btn_minus.setFixedSize(44, 26)
            btn_minus.setFocusPolicy(QtCore.Qt.NoFocus)

            btn_plus.clicked.connect(lambda _, c=ch: self._step_range(c, +1))
            btn_minus.clicked.connect(lambda _, c=ch: self._step_range(c, -1))

            btn_lay.addStretch()
            btn_lay.addWidget(btn_plus)
            btn_lay.addWidget(range_lbl)
            btn_lay.addWidget(btn_minus)
            btn_lay.addStretch()

            row_lay.addWidget(gw, stretch=1)
            row_lay.addWidget(btn_panel)
            vlay.addWidget(row, stretch=1)

            curves[ch]             = p.plot(pen=pg.mkPen(col, width=1.5))
            plots[ch]              = p
            self._range_idx[ch]    = None
            self._range_labels[ch] = range_lbl
            prev_per_group[g_idx]  = p

        return panel, curves, plots

    # ── shared panel helper ──────────────────────────────────────────────────

    def _make_panel(self, title: str):
        """Return (QWidget container, GraphicsLayoutWidget) for a panel."""
        panel = QtWidgets.QWidget()
        lay   = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        lbl = QtWidgets.QLabel(title)
        lbl.setObjectName("panelTitle")
        lay.addWidget(lbl)

        gw = pg.GraphicsLayoutWidget()
        gw.setBackground(_BG)
        lay.addWidget(gw)
        return panel, gw

    # ── status bar ───────────────────────────────────────────────────────────

    def _build_statusbar(self):
        sb_widget = QtWidgets.QWidget()
        sb_lay    = QtWidgets.QHBoxLayout(sb_widget)
        sb_lay.setContentsMargins(6, 0, 6, 0)
        sb_lay.setSpacing(0)

        self._lbl_time = QtWidgets.QLabel("  Waiting for data…")
        self._lbl_time.setFixedWidth(230)
        sb_lay.addWidget(self._lbl_time)

        self._ch_labels: dict = {}
        for i, ch in enumerate(self.channels):
            sep = QtWidgets.QFrame()
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setFrameShadow(QtWidgets.QFrame.Sunken)
            sep.setStyleSheet(f"color: {_GRID};")
            sb_lay.addWidget(sep)

            lbl = QtWidgets.QLabel(f"  {ch}: —  ")
            lbl.setStyleSheet(f"color: {_colour(i)}; font-weight: bold;")
            sb_lay.addWidget(lbl)
            self._ch_labels[ch] = lbl

        sb_lay.addStretch()
        self.statusBar().addPermanentWidget(sb_widget, 1)

    # ── queue polling ────────────────────────────────────────────────────────

    def _poll(self):
        changed: set = set()

        while True:
            try:
                item = self.update_queue.get_nowait()
            except queue.Empty:
                break

            if item.get("type") == "error":
                self._show_error(item.get("message", "Unknown error"))
                continue

            ch = item.get("channel_name")
            if ch not in self.channels:
                continue

            self._ts[ch].append(item["timestamp"])
            self._val[ch].append(item["value"])
            wfm_v = np.asarray(item["wfm"]) * 1e-3   # mV → V
            self._wfm_curves[ch].setData(
                np.asarray(item["wfm_t"]) * 1e-9,    # ns → s  (pyqtgraph shows µs)
                wfm_v,
            )
            if self._range_idx[ch] is None:
                idx = _pick_range_idx(wfm_v)
                self._range_idx[ch] = idx
                ymin, ymax = _yrange_from_signed(_SIGNED_RANGES[idx])
                self._wfm_plots[ch].setYRange(ymin, ymax, padding=0)
                self._wfm_plots[ch].enableAutoRange(axis='y', enable=False)
                self._range_labels[ch].setText(_fmt_range(_SIGNED_RANGES[idx]))
            self._ch_labels[ch].setText(f"  {ch}: {item['value']:.4g}  ")
            changed.add(ch)

        if changed:
            for ch in changed:
                if self._ts[ch]:
                    self._trend_curves[ch].setData(
                        np.array(self._ts[ch]),
                        np.array(self._val[ch]),
                    )
            self._lbl_time.setText(
                f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}"
            )

    def _show_error(self, message: str):
        self._lbl_time.setText(f"  ⚠  {message}")
        self._lbl_time.setStyleSheet(
            f"color: #f38ba8; font-weight: bold;"   # Catppuccin red
        )
        self._lbl_time.setFixedWidth(600)

    def _step_range(self, ch: str, direction: int):
        """Shift the Y range of channel *ch* one step up (+1) or down (−1)."""
        idx = self._range_idx.get(ch)
        if idx is None:
            return   # auto-range not yet set; ignore
        new_idx = max(0, min(len(_SIGNED_RANGES) - 1, idx + direction))
        if new_idx == idx:
            return
        self._range_idx[ch] = new_idx
        rv = _SIGNED_RANGES[new_idx]
        self._wfm_plots[ch].setYRange(*_yrange_from_signed(rv), padding=0)
        self._range_labels[ch].setText(_fmt_range(rv))

    # ── window close ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()


# ---------------------------------------------------------------------------
# Snapshot monitor — public entry point
# ---------------------------------------------------------------------------

class H2SnapshotApp:
    """
    Real-time monitor for snapshot-mode acquisition.

    Displays averaged waveforms updated every ``refresh_trigger_cnt`` triggers,
    plus a statistics strip showing peak-area mean ± standard error.

    Parameters
    ----------
    channels : list[str]
        Channel index letters, e.g. ``["A", "B"]``.  Used to look up
        ``"Ch{x}"`` keys in queue items.
    channel_labels : list[str]
        Human-readable label for each channel (same order as *channels*),
        e.g. ``["Sig", "Trig"]``.
    update_queue : queue.Queue
        Queue fed by H2LaserDigitizer snapshot threads.  Each item::

            {
                "device":      str,
                "t":           array,   # time axis [ns]
                "area_avg":    float,   # mean peak area [nV·s]
                "area_std":    float,   # std of peak area [nV·s]
                "trigger_cnt": int,     # triggers averaged
                "ChA":         array,   # avg waveform for channel A [mV]
                "ChB":         array,   # (and so on for other channels)
            }
    title : str, optional
        Window title suffix shown in the title bar.
    """

    def __init__(self, channels: list, channel_labels: list,
                 update_queue: queue.Queue, title: str = "",
                 signal_channel: str = ""):
        pg.setConfigOption("background", _BG)
        pg.setConfigOption("foreground", _FG)
        pg.setConfigOption("antialias", True)
        self._app = pg.mkQApp("H2Laser Snapshot Monitor")
        # Default signal channel is the first in the list
        sig_ch = signal_channel if signal_channel else channels[0]
        self._win = _SnapshotWindow(channels, channel_labels,
                                    update_queue, title, sig_ch)
        self._win.show()

    def run(self):
        """Start the Qt event loop; returns only when the window is closed."""
        try:
            pg.exec()
        except KeyboardInterrupt:
            self._win.close()


# ---------------------------------------------------------------------------
# Snapshot window
# ---------------------------------------------------------------------------

class _SnapshotWindow(QtWidgets.QMainWindow):

    _POLL_MS = 100   # queue-poll interval → 10 Hz refresh

    def __init__(self, channels: list, channel_labels: list,
                 update_queue: queue.Queue, title: str,
                 signal_channel: str = ""):
        super().__init__()
        self.channels       = channels        # e.g. ["A", "B"]
        self.channel_labels = channel_labels  # e.g. ["Sig", "Trig"]
        self.update_queue   = update_queue
        self._signal_ch    = signal_channel if signal_channel else channels[0]
        self._last_item    = None   # most recent data packet from the queue
        self._frozen_area  = None   # nV·s area of the frozen reference (None = no ref)
        self._paused       = False  # True while DAQ display is paused

        win_title = "H2Laser Snapshot Monitor  (v3)"
        if title:
            win_title = f"{win_title}  —  {title}"
        self.setWindowTitle(win_title)
        self.resize(1000, 700)
        _apply_dark_style(self)
        self._build_ui()
        _setup_sigint(self)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self._POLL_MS)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        vlay = QtWidgets.QVBoxLayout(root)
        vlay.setContentsMargins(8, 8, 8, 4)
        vlay.setSpacing(4)

        # ── waveform panel ───────────────────────────────────────────────────
        wfm_panel, self._wfm_curves, self._wfm_plots = self._make_wfm_panel()
        vlay.addWidget(wfm_panel, stretch=1)

        # ── statistics strip ─────────────────────────────────────────────────
        stats_bar = self._make_stats_bar()
        vlay.addWidget(stats_bar)

        # ── status bar ───────────────────────────────────────────────────────
        self._lbl_time = QtWidgets.QLabel("  Waiting for data…")
        self.statusBar().addPermanentWidget(self._lbl_time)

    # ── waveform panel ───────────────────────────────────────────────────────

    def _make_wfm_panel(self):
        panel = QtWidgets.QWidget()
        vlay  = QtWidgets.QVBoxLayout(panel)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(2)

        title_lbl = QtWidgets.QLabel("Averaged Waveforms")
        title_lbl.setObjectName("panelTitle")
        vlay.addWidget(title_lbl)

        curves             = {}
        plots              = {}
        self._range_idx    = {}
        self._range_labels = {}
        self._frozen_curves = {}   # channel → PlotDataItem with dashed reference
        prev = None
        n    = len(self.channels)

        for i, (ch, label) in enumerate(zip(self.channels,
                                             self.channel_labels)):
            col = _colour(i)

            # ── per-channel row ──────────────────────────────────────────────
            row     = QtWidgets.QWidget()
            row_lay = QtWidgets.QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(2)

            gw = pg.GraphicsLayoutWidget()
            gw.setBackground(_BG)
            p  = gw.addPlot(row=0, col=0, viewBox=_ZoomPanViewBox())
            p.setLabel("left", label, units="V", color=col, size="10pt")
            p.showGrid(x=True, y=True, alpha=0.20)
            p.getAxis("left").setWidth(75)
            if i < n - 1:
                p.hideAxis("bottom")
            else:
                p.setLabel("bottom", "Time", units="s")
            if prev is not None:
                p.setXLink(prev)

            # ── range-control buttons ────────────────────────────────────────
            btn_panel = QtWidgets.QWidget()
            btn_panel.setFixedWidth(52)
            btn_lay   = QtWidgets.QVBoxLayout(btn_panel)
            btn_lay.setContentsMargins(2, 4, 2, 4)
            btn_lay.setSpacing(2)

            btn_plus  = QtWidgets.QPushButton("+")
            btn_plus.setFixedSize(44, 26)
            btn_plus.setFocusPolicy(QtCore.Qt.NoFocus)

            range_lbl = QtWidgets.QLabel("—")
            range_lbl.setAlignment(QtCore.Qt.AlignCenter)
            range_lbl.setStyleSheet(f"color: {col}; font-size: 10px;")

            btn_minus = QtWidgets.QPushButton("−")
            btn_minus.setFixedSize(44, 26)
            btn_minus.setFocusPolicy(QtCore.Qt.NoFocus)

            btn_plus.clicked.connect(lambda _, c=ch: self._step_range(c, +1))
            btn_minus.clicked.connect(lambda _, c=ch: self._step_range(c, -1))

            btn_lay.addStretch()
            btn_lay.addWidget(btn_plus)
            btn_lay.addWidget(range_lbl)
            btn_lay.addWidget(btn_minus)
            btn_lay.addStretch()

            row_lay.addWidget(gw, stretch=1)
            row_lay.addWidget(btn_panel)
            vlay.addWidget(row, stretch=1)

            curves[ch]              = p.plot(pen=pg.mkPen(col, width=2))
            # dashed reference curve — hidden until frozen
            self._frozen_curves[ch] = p.plot(
                pen=pg.mkPen(col, width=1.5,
                             style=QtCore.Qt.DashLine)
            )
            plots[ch]              = p
            self._range_idx[ch]    = None
            self._range_labels[ch] = range_lbl
            prev = p

        return panel, curves, plots

    # ── statistics strip ─────────────────────────────────────────────────────

    def _make_stats_bar(self):
        bar = QtWidgets.QWidget()
        bar.setFixedHeight(40)
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(0)

        def _sep():
            f = QtWidgets.QFrame()
            f.setObjectName("statsSep")
            f.setFrameShape(QtWidgets.QFrame.VLine)
            f.setFrameShadow(QtWidgets.QFrame.Sunken)
            return f

        self._lbl_device   = QtWidgets.QLabel("  Device: —")
        self._lbl_device.setObjectName("statsLabel")

        self._lbl_area     = QtWidgets.QLabel("  Area: —")
        self._lbl_area.setObjectName("statsLabel")
        self._lbl_area.setStyleSheet(
            f"color: {_colour(0)}; font-weight: bold; font-size: 13px;"
            f"padding: 2px 10px; background: {_SURF}; border-radius: 4px;"
        )

        self._lbl_n        = QtWidgets.QLabel("  N: —")
        self._lbl_n.setObjectName("statsLabel")

        # ── Pause / Resume toggle button ─────────────────────────────────────
        self._pause_btn = QtWidgets.QPushButton("Pause")
        self._pause_btn.setFixedSize(72, 28)
        self._pause_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self._pause_btn.clicked.connect(self._on_pause)

        # ── Freeze / Clear toggle button ─────────────────────────────────────
        self._freeze_btn = QtWidgets.QPushButton("Freeze")
        self._freeze_btn.setFixedSize(72, 28)
        self._freeze_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self._freeze_btn.clicked.connect(self._on_freeze)

        # ── Math result label ────────────────────────────────────────────────
        self._lbl_math = QtWidgets.QLabel("")
        self._lbl_math.setObjectName("statsLabel")
        self._lbl_math.setStyleSheet(
            f"color: #f9e2af; font-weight: bold; font-size: 13px;"   # yellow
            f"padding: 2px 10px; background: {_SURF}; border-radius: 4px;"
        )

        # ── Save button ───────────────────────────────────────────────────────
        self._save_btn = QtWidgets.QPushButton("Save")
        self._save_btn.setFixedSize(60, 28)
        self._save_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self._save_btn.clicked.connect(self._on_save)

        lay.addWidget(self._lbl_device)
        lay.addWidget(_sep())
        lay.addWidget(self._lbl_area)
        lay.addWidget(_sep())
        lay.addWidget(self._lbl_n)
        lay.addWidget(_sep())
        lay.addWidget(self._pause_btn)
        lay.addWidget(_sep())
        lay.addWidget(self._freeze_btn)
        lay.addWidget(_sep())
        lay.addWidget(self._lbl_math)
        lay.addStretch()
        lay.addWidget(self._save_btn)
        return bar

    # ── freeze / math ────────────────────────────────────────────────────────

    def _on_pause(self):
        """Toggle pause: when paused the display freezes; DAQ data is discarded."""
        self._paused = not self._paused
        self._pause_btn.setText("Resume" if self._paused else "Pause")

    def _on_freeze(self):
        """Toggle the frozen reference waveform for the signal channel only."""
        if self._frozen_area is None:
            # ── Freeze: capture signal channel waveform as reference ─────────
            if self._last_item is None:
                return   # nothing to freeze yet
            item = self._last_item
            t    = item.get("t")
            ch   = self._signal_ch
            wfm  = item.get(f"Ch{ch}")
            if wfm is not None and t is not None:
                self._frozen_curves[ch].setData(
                    np.asarray(t)   * 1e-9,
                    np.asarray(wfm) * 1e-3,
                )
            self._frozen_area = item.get("area_avg", 0.0)
            self._freeze_btn.setText("Clear")
            self._lbl_math.setText("  Math: computing…")
        else:
            # ── Clear: remove frozen reference ───────────────────────────────
            self._frozen_curves[self._signal_ch].setData([], [])
            self._frozen_area = None
            self._freeze_btn.setText("Freeze")
            self._lbl_math.setText("")

    def _on_save(self):
        """Save the signal-channel waveform (and frozen reference if present) to CSV."""
        if self._last_item is None:
            return   # nothing captured yet

        item   = self._last_item
        ch     = self._signal_ch
        t_raw  = item.get("t")
        wfm    = item.get(f"Ch{ch}")
        if t_raw is None or wfm is None:
            return

        t_s    = np.asarray(t_raw)  * 1e-9   # ns → s
        live_v = np.asarray(wfm)    * 1e-3   # mV → V

        area_avg = item.get("area_avg", 0.0)
        area_std = item.get("area_std", 0.0)
        n        = item.get("trigger_cnt", 1)
        device   = item.get("device", "—")
        stderr   = area_std / math.sqrt(max(n, 1))

        # Resolve signal channel label
        try:
            ch_label = self.channel_labels[self.channels.index(ch)]
        except ValueError:
            ch_label = ch

        # Frozen waveform (from PlotDataItem.getData())
        frozen_t, frozen_v = self._frozen_curves[ch].getData()
        has_frozen = (frozen_t is not None and len(frozen_t) > 0)

        # ── auto-name: snapshot_DEVICE_YYYYMMDD_NNN.csv ─────────────────────
        os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
        # Sanitise device name for use in a filename
        dev_tag  = "".join(c if c.isalnum() or c in "-_" else "_"
                           for c in device).strip("_") or "unknown"
        date_tag = datetime.now().strftime("%Y%m%d")
        prefix   = f"snapshot_{dev_tag}_{date_tag}_"
        existing = [
            f for f in os.listdir(_SNAPSHOT_DIR)
            if f.startswith(prefix) and f.endswith(".csv")
        ]
        nums = []
        for f in existing:
            try:
                nums.append(int(f[len(prefix):-4]))
            except ValueError:
                pass
        seq = (max(nums) + 1) if nums else 1
        fname = os.path.join(_SNAPSHOT_DIR, f"{prefix}{seq:03d}.csv")

        # ── write CSV ────────────────────────────────────────────────────────
        with open(fname, "w") as fp:
            fp.write("# H2LaserDAQ Snapshot\n")
            fp.write(f"# Saved   : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}\n")
            fp.write(f"# Device  : {device}\n")
            fp.write(f"# Channel : {ch} ({ch_label})\n")
            fp.write(f"# Area (live)  : {area_avg:.6g} ± {stderr:.4g}  nV·s"
                     f"  (N = {n} triggers)\n")
            if has_frozen:
                math_val = area_avg - self._frozen_area
                fp.write(f"# Area (frozen): {self._frozen_area:.6g}  nV·s\n")
                fp.write(f"# Area (Math)  : {math_val:+.6g}  nV·s\n")
            fp.write("#\n")

            if has_frozen:
                fp.write("time_s,live_V,frozen_V\n")
                # frozen may have different length — interpolate onto live grid
                frozen_v_interp = np.interp(t_s, frozen_t, frozen_v,
                                            left=np.nan, right=np.nan)
                for ts, lv, fv in zip(t_s, live_v, frozen_v_interp):
                    fp.write(f"{ts:.6e},{lv:.6e},{fv:.6e}\n")
            else:
                fp.write("time_s,live_V\n")
                for ts, lv in zip(t_s, live_v):
                    fp.write(f"{ts:.6e},{lv:.6e}\n")

        print(f"[SAVE] Snapshot saved → {fname}")
        # Brief visual feedback on the status bar
        orig = self._lbl_time.text()
        self._lbl_time.setText(f"  Saved: {os.path.basename(fname)}")
        QtCore.QTimer.singleShot(3000, lambda: self._lbl_time.setText(orig))

    # ── queue polling ────────────────────────────────────────────────────────

    def _poll(self):
        item = None
        # drain queue, keep only the latest data packet;
        # handle error sentinels immediately as they arrive.
        while True:
            try:
                candidate = self.update_queue.get_nowait()
            except queue.Empty:
                break
            if candidate.get("type") == "error":
                self._show_error(candidate.get("message", "Unknown error"))
                continue
            item = candidate

        if item is None or self._paused:
            return

        self._last_item = item   # keep for Freeze capture

        t          = item.get("t")
        area_avg   = item.get("area_avg", 0.0)
        area_std   = item.get("area_std", 0.0)
        n          = item.get("trigger_cnt", 1)
        device     = item.get("device", "—")

        for ch in self.channels:
            wfm = item.get(f"Ch{ch}")
            if wfm is not None and t is not None:
                wfm_v = np.asarray(wfm) * 1e-3   # mV → V
                self._wfm_curves[ch].setData(
                    np.asarray(t) * 1e-9,          # ns → s  (pyqtgraph shows µs)
                    wfm_v,
                )
                if self._range_idx[ch] is None:
                    idx = _pick_range_idx(wfm_v)
                    self._range_idx[ch] = idx
                    ymin, ymax = _yrange_from_signed(_SIGNED_RANGES[idx])
                    self._wfm_plots[ch].setYRange(ymin, ymax, padding=0)
                    self._wfm_plots[ch].enableAutoRange(axis='y', enable=False)
                    self._range_labels[ch].setText(_fmt_range(_SIGNED_RANGES[idx]))

        stderr = area_std / math.sqrt(max(n, 1))
        self._lbl_device.setText(f"  Device: {device}")
        self._lbl_area.setText(
            f"  Peak area: {area_avg:.4g} ± {stderr:.3g}  nV·s"
        )
        self._lbl_n.setText(f"  N = {n} triggers")
        self._lbl_time.setText(
            f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}  "
        )

        if self._frozen_area is not None:
            math_val = area_avg - self._frozen_area
            self._lbl_math.setText(
                f"  Math: {math_val:+.4g}  nV·s"
            )

    def _show_error(self, message: str):
        self._lbl_time.setText(f"  ⚠  {message}")
        self._lbl_time.setStyleSheet(
            f"color: #f38ba8; font-weight: bold;"   # Catppuccin red
        )

    def _step_range(self, ch: str, direction: int):
        """Shift the Y range of channel *ch* one step up (+1) or down (−1)."""
        idx = self._range_idx.get(ch)
        if idx is None:
            return   # auto-range not yet set; ignore
        new_idx = max(0, min(len(_SIGNED_RANGES) - 1, idx + direction))
        if new_idx == idx:
            return
        self._range_idx[ch] = new_idx
        rv = _SIGNED_RANGES[new_idx]
        self._wfm_plots[ch].setYRange(*_yrange_from_signed(rv), padding=0)
        self._range_labels[ch].setText(_fmt_range(rv))

    # ── window close ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()
