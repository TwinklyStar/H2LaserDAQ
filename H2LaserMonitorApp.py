# h2_monitor.py
import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import queue
from collections import deque

class H2MonitorApp:
    def __init__(self, channels, update_queue):
        """
        monitor_config: dict from h2_config.MONITOR_CONFIG
        update_queue: queue from H2LaserDAQManager
        """
        self.update_queue = update_queue
        self.channels = channels
        self.times = {} 
        self.values = {}
        self.times = {ch: deque(maxlen=4000) for ch in self.channels}
        self.values = {ch: deque(maxlen=4000) for ch in self.channels}

        print("[MONITOR] Starting MonitorApp...")
        plt.ion()
        n = len(self.channels)
        self.fig, axes = plt.subplots(n, 1, sharex=True,
                                      figsize=(10, 3 * n))
        if n == 1:
            axes = [axes]

        self.axes = {}
        self.lines = {}

        for ax, ch in zip(axes, channels):
            line, = ax.plot([], [], marker=",", linestyle="-")
            ax.set_ylabel(fr"{ch} integrated area [mV$\times$ns]")
            self.axes[ch] = ax
            self.lines[ch] = line

        axes[-1].set_xlabel("Time")
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m-%d %H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        self.fig.autofmt_xdate()
        self.fig_wfm.tight_layout()
        self.fig.suptitle(r"H2Laser DAQ Monitor (mV$\times$ns)")


        self.fig_wfm, axes_wfm = plt.subplots(n, 1, sharex=True,
                                      figsize=(10, 3 * n))
        if n == 1:
            axes_wfm = [axes_wfm]

        self.axes_wfm = {}
        self.lines_wfm = {}

        for ax, ch in zip(axes_wfm, channels):
            line_wfm, = ax.plot([], [], marker=",", linestyle="-")
            ax.set_ylabel("f{ch} [mV]")
            self.axes_wfm[ch] = ax
            self.lines_wfm[ch] = line_wfm

        axes_wfm[-1].set_xlabel("Time [ns]")

        self.fig_wfm.suptitle("H2Laser Waveform Monitor")

        self.running = False

        # stop loop when close the GUI
        def on_close(event):
            self.running = False
        self.fig.canvas.mpl_connect("close_event", on_close)
        self.fig_wfm.canvas.mpl_connect("close_event", on_close)

    def run(self):
        self.running = True
        try:
            while self.running:
                # Take all data in queue
                while True:
                    try:
                        item = self.update_queue.get_nowait()
                    except queue.Empty:
                        break

                    ch = item["channel_name"]       
                    ts = item["timestamp"]
                    val = item["value"]
                    self.wfm_t = item["wfm_t"]
                    self.wfm = item["wfm"]

                    if ch not in self.channels:
                        continue

                    dt = datetime.fromtimestamp(ts)
                    self.times[ch].append(dt)
                    self.values[ch].append(val)

                any_data = False
                for ch in self.channels:
                    if not self.times[ch]:
                        continue
                    any_data = True
                    line = self.lines[ch]
                    ax = self.axes[ch]

                    line.set_data(self.times[ch], self.values[ch])
                    ax.relim()
                    ax.autoscale_view()

                    line_wfm = self.lines_wfm[ch]
                    ax_wfm = self.axes_wfm[ch]
                    line_wfm.set_data(self.wfm_t, self.wfm)
                    ax_wfm.relim()
                    ax_wfm.autoscale_view()

                if any_data:
                    self.fig.canvas.draw()
                    self.fig.canvas.flush_events()
                    self.fig_wfm.canvas.draw()
                    self.fig_wfm.canvas.flush_events()

                time.sleep(0.1)   
        except KeyboardInterrupt:
            plt.ioff()
            plt.close(self.fig)
            plt.close(self.fig_wfm)
            print("[EXIT] Ctrl+C received. Monitor closed")