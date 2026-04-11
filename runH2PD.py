from config.config_H2PD import DIGITIZER_CONFIGS
from src.H2LaserDAQManager import H2LaserDAQManager
from src.H2LaserMonitorApp import H2SnapshotApp
from datetime import datetime


def main():
    print("==============================================")
    print("       H2 VUV Photodiode Snapshot")
    print("       Start time:", datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    print("==============================================\n")

    cfg = next(iter(DIGITIZER_CONFIGS.values()))
    daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)

    monitor = H2SnapshotApp(
        channels=cfg["channels"],
        channel_labels=cfg["channel_name"],
        update_queue=daq_manager.update_queue,
        title="H2 VUV Photodiode",
    )

    daq_manager.start_all()

    try:
        monitor.run()
    finally:
        daq_manager.stop_all()
        print("\n==============================================")
        print("       H2 VUV Photodiode ended normally.")
        print("==============================================")


if __name__ == "__main__":
    main()
