# h2_monitor.py
import time

class H2MonitorApp:
    def __init__(self, monitor_config, update_queue):
        """
        monitor_config: dict from h2_config.MONITOR_CONFIG
        update_queue: queue from H2LaserDAQManager
        """
        self.monitor_config = monitor_config
        self.update_queue = update_queue
        self.time_window_default = monitor_config.get("time_window_default", "1h")
        self.time_windows = monitor_config.get("time_windows", [])
        self.refresh_interval = monitor_config.get("refresh_interval_sec", 1.0)

        # TODO: set up GUI window + plots later

    def run(self):
        """
        For now: just print what we receive.
        Later: this will be your GUI event loop.
        """
        try:
            while True:
                try:
                    item = self.update_queue.get(timeout=self.refresh_interval)
                    print("Monitor received:", item)
                    # TODO: update plots here
                except Exception:
                    # Timeout -> no new data, can do GUI idle tasks
                    pass
        except KeyboardInterrupt:
            print("Monitor stopped.")