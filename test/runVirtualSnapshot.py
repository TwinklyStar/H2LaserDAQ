# runVirtualSnapshot.py
# Virtual snapshot-mode DAQ test — no hardware required.
#
# Simulates the full snapshot-mode pipeline:
#   VirtualDigitizer thread  →  ROOT output  +  GUI update queue
#   H2SnapshotApp            →  live averaged waveform + peak-area statistics
#
# Run from project root:
#   python3 test/runVirtualSnapshot.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import queue
import threading

from test.VirtualDigitizer import VirtualDigitizer
from test.config_virtual_snapshot import VIRTUAL_CONFIGS
from src.H2LaserMonitorApp import H2SnapshotApp
from src.banner import print_banner, print_footer


def main():
    print_banner("Virtual DAQ  —  Snapshot Mode Test  (no hardware)")

    update_queue = queue.Queue()
    stop_event   = threading.Event()

    cfg_name, cfg = next(iter(VIRTUAL_CONFIGS.items()))
    worker = VirtualDigitizer(
        name=cfg_name,
        config=cfg,
        update_queue=update_queue,
        stop_event=stop_event,
    )

    monitor = H2SnapshotApp(
        channels=cfg["channels"],
        channel_labels=cfg["channel_name"],
        update_queue=update_queue,
        title="Virtual Snapshot",
        signal_channel=cfg.get("snapshot_channel", cfg["channels"][0]),
    )

    worker.start()

    try:
        monitor.run()
    finally:
        stop_event.set()
        print("\n[EXIT] Stopping virtual digitizer thread...")
        worker.join()
        worker.close()
        print_footer("Virtual Snapshot Test")


if __name__ == "__main__":
    main()
