# runVirtualContinuous.py
# Virtual continuous-mode DAQ test — no hardware required.
#
# Simulates the full continuous-mode pipeline:
#   VirtualDigitizer thread(s)  →  ROOT + CSV output  +  GUI update queue
#   H2MonitorApp (main thread)  →  real-time matplotlib signal & waveform plots
#
# Run from project root:
#   python3 test/runVirtualContinuous.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import queue
import threading

from test.VirtualDigitizer import VirtualDigitizer
from test.config_virtual_continuous import VIRTUAL_CONFIGS
from src.H2LaserMonitorApp import H2MonitorApp
from src.banner import print_banner, print_footer


def main():
    print_banner("Virtual DAQ  —  Continuous Mode Test  (no hardware)")

    update_queue = queue.Queue()
    stop_event   = threading.Event()

    # Instantiate one VirtualDigitizer per config entry
    workers = {}
    for name, cfg in VIRTUAL_CONFIGS.items():
        workers[name] = VirtualDigitizer(
            name=name,
            config=cfg,
            update_queue=update_queue,
            stop_event=stop_event,
        )

    # Collect all channel names in config order for the GUI
    channels = [
        ch_name
        for cfg in VIRTUAL_CONFIGS.values()
        for ch_name in cfg["channel_name"]
    ]

    monitor = H2MonitorApp(channels=channels, update_queue=update_queue)

    for w in workers.values():
        w.start()

    try:
        monitor.run()
    finally:
        stop_event.set()
        print("\n[EXIT] Stopping virtual digitizer threads...")
        for w in workers.values():
            w.join()
            w.close()
        print_footer("Virtual Continuous Test")


if __name__ == "__main__":
    main()
