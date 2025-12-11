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
        self.times = {ch: deque(maxlen=2000) for ch in self.channels}
        self.values = {ch: deque(maxlen=2000) for ch in self.channels}

        # TODO: set up GUI window + plots later
        plt.ion()
        n = len(self.channels)
        self.fig, axes = plt.subplots(n, 1, sharex=True,
                                      figsize=(8, 2.5 * n))
        if n == 1:
            axes = [axes]

        self.axes = {}
        self.lines = {}

        for ax, ch in zip(axes, channels):
            line, = ax.plot([], [], marker=".", linestyle="-")
            ax.set_ylabel(ch)
            self.axes[ch] = ax
            self.lines[ch] = line

        axes[-1].set_xlabel("Time")
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m-%d %H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        self.fig.autofmt_xdate()
        self.fig.suptitle("H2Laser DAQ Monitor")

        self.running = False

        # stop loop when close the GUI
        def on_close(event):
            self.running = False
        self.fig.canvas.mpl_connect("close_event", on_close)

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

                if any_data:
                    self.fig.canvas.draw()
                    self.fig.canvas.flush_events()

                time.sleep(0.1)   
        except KeyboardInterrupt:
            plt.ioff()
            plt.close(self.fig)
            print("Monitor stopped.")