from config.config_H2PD import DIGITIZER_CONFIGS
from src.H2LaserDAQManager import H2LaserDAQManager
from src.H2LaserMonitorApp import H2SnapshotApp
from src.banner import print_banner, print_footer


def main():
    print_banner("H2 VUV Photodiode  (snapshot mode)")

    cfg = next(iter(DIGITIZER_CONFIGS.values()))
    try:
        daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)
    except SystemExit:
        print("[FATAL] DAQ could not start. Program terminated.")
        return

    monitor = H2SnapshotApp(
        channels=cfg["channels"],
        channel_labels=cfg["channel_name"],
        update_queue=daq_manager.update_queue,
        title="H2 VUV Photodiode",
        signal_channel=cfg.get("snapshot_channel", cfg["channels"][0]),
    )

    daq_manager.start_all()

    try:
        monitor.run()
    finally:
        daq_manager.stop_all()
        print_footer("H2 VUV Photodiode")


if __name__ == "__main__":
    main()
