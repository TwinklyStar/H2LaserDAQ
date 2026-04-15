from src.H2LaserDAQManager import H2LaserDAQManager
from src.H2LaserMonitorApp import H2MonitorApp


def main(digitizer_configs: dict) -> None:
    # Validate that every device in the config is continuous mode
    for name, cfg in digitizer_configs.items():
        if cfg.get("run_mode") != "continuous":
            raise ValueError(
                f"Device '{name}' has run_mode='{cfg.get('run_mode')}' — "
                f"expected 'continuous'. Use the Snapshot Monitor instead."
            )

    try:
        daq_manager = H2LaserDAQManager(digitizer_configs)
    except SystemExit:
        print("[FATAL] DAQ could not start. Program terminated.")
        return

    # Build flat channel list and per-digitizer groups for X-axis linking
    displayed      = [n for cfg in digitizer_configs.values()
                        for n in cfg["channel_name"]]
    channel_groups = [list(cfg["channel_name"])
                      for cfg in digitizer_configs.values()]

    monitor = H2MonitorApp(
        channels=displayed,
        update_queue=daq_manager.update_queue,
        channel_groups=channel_groups,
    )

    daq_manager.start_all()

    try:
        monitor.run()
    finally:
        daq_manager.stop_all()
