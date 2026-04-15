# runH2LaserDAQ.py
from config.config import DIGITIZER_CONFIGS
from src.H2LaserDAQManager import H2LaserDAQManager
from src.H2LaserMonitorApp import H2MonitorApp
from src.banner import print_banner, print_footer
from src.H2Exceptions import DigitizerInitError

def main():

    print_banner("H2 Laser Room DAQ  (continuous mode)")
    # Pass macro configs into the classes
    try:
        daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)
    except SystemExit:
        print("[FATAL] DAQ could not start. Program terminated.")
        return
    displayed = ["355", "212", "820", "NO_cell"]
    channel_groups = [
        [name for name in cfg["channel_name"] if name in displayed]
        for cfg in DIGITIZER_CONFIGS.values()
    ]
    monitor = H2MonitorApp(
        channels=displayed,
        update_queue=daq_manager.update_queue,
        channel_groups=channel_groups,
    )

    daq_manager.start_all()

    try:
        # This will be your monitor GUI main loop eventually
        monitor.run()
    # try:
    #     while True:
    #         time.sleep(1)
    finally:
        # On exit (or error), stop all digitizer threads cleanly
        daq_manager.stop_all()

        print_footer("H2 Laser Room DAQ")

if __name__ == "__main__":
    main()