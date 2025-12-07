# runH2LaserDAQ.py
# from config import DIGITIZER_CONFIGS, MONITOR_CONFIG
from config import DIGITIZER_CONFIGS
from H2LaserDAQManager import H2LaserDAQManager
from H2LaserMonitorApp import H2MonitorApp
import time

def main():
    # Pass macro configs into the classes
    daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)
    # monitor = H2MonitorApp(MONITOR_CONFIG, daq_manager.update_queue)

    daq_manager.start_all()

    # try:
    #     # This will be your monitor GUI main loop eventually
    #     monitor.run()
    try:
        while True:
            time.sleep(1)
    finally:
        # On exit (or error), stop all digitizer threads cleanly
        daq_manager.stop_all()

if __name__ == "__main__":
    main()