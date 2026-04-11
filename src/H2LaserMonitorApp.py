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

import queue
import signal
from collections import deque
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore

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
                "value":        float,   # integrated area [mV·ns]
                "wfm_t":        array,   # time axis [ns]
                "wfm":          array,   # voltage [mV]
            }
    """

    def __init__(self, channels: list, update_queue: queue.Queue):
        pg.setConfigOption("background", _BG)
        pg.setConfigOption("foreground", _FG)
        pg.setConfigOption("antialias", True)
        self._app = pg.mkQApp("H2Laser DAQ Monitor")
        self._win = _MonitorWindow(channels, update_queue)
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

    def __init__(self, channels: list, update_queue: queue.Queue):
        super().__init__()
        self.channels     = channels
        self.update_queue = update_queue

        self._ts  = {ch: deque(maxlen=self._BUFFER) for ch in channels}
        self._val = {ch: deque(maxlen=self._BUFFER) for ch in channels}

        self.setWindowTitle("H2Laser DAQ Monitor  (v2.0)")
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

        trend_panel, self._trend_curves = self._make_trend_panel()
        wfm_panel,   self._wfm_curves   = self._make_wfm_panel()
        splitter.addWidget(trend_panel)
        splitter.addWidget(wfm_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 600])

        self._build_statusbar()

    # ── trend panel ──────────────────────────────────────────────────────────

    def _make_trend_panel(self):
        panel, gw = self._make_panel("Signal Trends  (mV·ns)")
        curves    = {}
        prev      = None
        n         = len(self.channels)

        for i, ch in enumerate(self.channels):
            col       = _colour(i)
            date_axis = pg.DateAxisItem(orientation="bottom")
            p = gw.addPlot(row=i, col=0, axisItems={"bottom": date_axis})
            p.setLabel("left", ch, units="mV·ns", color=col, size="10pt")
            # Compound unit — disable SI prefix to prevent "kmV·ns" etc.
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
        panel, gw = self._make_panel("Live Waveforms")
        curves    = {}
        prev      = None
        n         = len(self.channels)

        for i, ch in enumerate(self.channels):
            col = _colour(i)
            p = gw.addPlot(row=i, col=0)
            # Use base SI units so pyqtgraph auto-scales to mV, µs, etc.
            p.setLabel("left", ch, units="V", color=col, size="10pt")
            p.showGrid(x=True, y=True, alpha=0.20)
            p.getAxis("left").setWidth(75)
            if i < n - 1:
                p.hideAxis("bottom")
            else:
                p.setLabel("bottom", "Time", units="s")
            if prev is not None:
                p.setXLink(prev)
            curves[ch] = p.plot(pen=pg.mkPen(col, width=1.5))
            gw.ci.layout.setRowStretchFactor(i, 1)
            prev = p

        return panel, curves

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

            ch = item.get("channel_name")
            if ch not in self.channels:
                continue

            self._ts[ch].append(item["timestamp"])
            self._val[ch].append(item["value"])
            self._wfm_curves[ch].setData(
                np.asarray(item["wfm_t"]) * 1e-9,   # ns → s  (pyqtgraph shows µs)
                np.asarray(item["wfm"])   * 1e-3,   # mV → V  (pyqtgraph shows mV)
            )
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
                "area_avg":    float,   # mean peak area [mV·ns]
                "area_std":    float,   # std of peak area [mV·ns]
                "trigger_cnt": int,     # triggers averaged
                "ChA":         array,   # avg waveform for channel A [mV]
                "ChB":         array,   # (and so on for other channels)
            }
    title : str, optional
        Window title suffix shown in the title bar.
    """

    def __init__(self, channels: list, channel_labels: list,
                 update_queue: queue.Queue, title: str = ""):
        pg.setConfigOption("background", _BG)
        pg.setConfigOption("foreground", _FG)
        pg.setConfigOption("antialias", True)
        self._app = pg.mkQApp("H2Laser Snapshot Monitor")
        self._win = _SnapshotWindow(channels, channel_labels,
                                    update_queue, title)
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
                 update_queue: queue.Queue, title: str):
        super().__init__()
        self.channels       = channels        # e.g. ["A", "B"]
        self.channel_labels = channel_labels  # e.g. ["Sig", "Trig"]
        self.update_queue   = update_queue

        win_title = "H2Laser Snapshot Monitor  (v2.0)"
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
        wfm_panel, self._wfm_curves = self._make_wfm_panel()
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
        lay   = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        title_lbl = QtWidgets.QLabel("Averaged Waveforms  (mV)")
        title_lbl.setObjectName("panelTitle")
        lay.addWidget(title_lbl)

        gw = pg.GraphicsLayoutWidget()
        gw.setBackground(_BG)
        lay.addWidget(gw)

        curves = {}
        prev   = None
        n      = len(self.channels)

        for i, (ch, label) in enumerate(zip(self.channels,
                                             self.channel_labels)):
            col = _colour(i)
            p = gw.addPlot(row=i, col=0)
            # Use base SI units so pyqtgraph auto-scales to mV, µs, etc.
            p.setLabel("left", label, units="V", color=col, size="10pt")
            p.showGrid(x=True, y=True, alpha=0.20)
            p.getAxis("left").setWidth(75)
            if i < n - 1:
                p.hideAxis("bottom")
            else:
                p.setLabel("bottom", "Time", units="s")
            if prev is not None:
                p.setXLink(prev)
            curves[ch] = p.plot(pen=pg.mkPen(col, width=2))
            gw.ci.layout.setRowStretchFactor(i, 1)
            prev = p

        return panel, curves

    # ── statistics strip ─────────────────────────────────────────────────────

    def _make_stats_bar(self):
        bar = QtWidgets.QWidget()
        bar.setFixedHeight(36)
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

        lay.addWidget(self._lbl_device)
        lay.addWidget(_sep())
        lay.addWidget(self._lbl_area)
        lay.addWidget(_sep())
        lay.addWidget(self._lbl_n)
        lay.addStretch()
        return bar

    # ── queue polling ────────────────────────────────────────────────────────

    def _poll(self):
        item = None
        # drain queue, keep only the latest packet
        while True:
            try:
                item = self.update_queue.get_nowait()
            except queue.Empty:
                break

        if item is None:
            return

        t          = item.get("t")
        area_avg   = item.get("area_avg", 0.0)
        area_std   = item.get("area_std", 0.0)
        n          = item.get("trigger_cnt", 1)
        device     = item.get("device", "—")

        for ch in self.channels:
            wfm = item.get(f"Ch{ch}")
            if wfm is not None and t is not None:
                self._wfm_curves[ch].setData(
                    np.asarray(t)   * 1e-9,   # ns → s  (pyqtgraph shows µs)
                    np.asarray(wfm) * 1e-3,   # mV → V  (pyqtgraph shows mV)
                )

        import math
        stderr = area_std / math.sqrt(max(n, 1))
        self._lbl_device.setText(f"  Device: {device}")
        self._lbl_area.setText(
            f"  Peak area: {area_avg:.4g} ± {stderr:.3g}  mV·ns"
        )
        self._lbl_n.setText(f"  N = {n} triggers")
        self._lbl_time.setText(
            f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}  "
        )

    # ── window close ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()
