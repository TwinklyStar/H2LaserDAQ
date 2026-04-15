from src.H2LaserDAQManager import H2LaserDAQManager
from src.H2LaserMonitorApp import H2SnapshotApp


def main(digitizer_configs: dict) -> None:
    # Snapshot mode is single-digitizer; validate and extract the one config
    if len(digitizer_configs) != 1:
        raise ValueError(
            f"Snapshot mode expects exactly one digitizer config, "
            f"got {len(digitizer_configs)}: {list(digitizer_configs.keys())}"
        )

    cfg_name, cfg = next(iter(digitizer_configs.items()))

    if cfg.get("run_mode") != "snapshot":
        raise ValueError(
            f"Device '{cfg_name}' has run_mode='{cfg.get('run_mode')}' — "
            f"expected 'snapshot'. Use the Continuous DAQ instead."
        )

    try:
        daq_manager = H2LaserDAQManager(digitizer_configs)
    except SystemExit:
        print("[FATAL] DAQ could not start. Program terminated.")
        return

    monitor = H2SnapshotApp(
        channels=cfg["channels"],
        channel_labels=cfg["channel_name"],
        update_queue=daq_manager.update_queue,
        title=cfg_name,
        signal_channel=cfg.get("snapshot_channel", cfg["channels"][0]),
    )

    daq_manager.start_all()

    try:
        monitor.run()
    finally:
        daq_manager.stop_all()
