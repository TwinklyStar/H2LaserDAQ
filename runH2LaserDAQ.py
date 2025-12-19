# runH2LaserDAQ.py
from config import DIGITIZER_CONFIGS
from H2LaserDAQManager import H2LaserDAQManager
from H2LaserMonitorApp import H2MonitorApp
import time
from datetime import datetime
from H2Exceptions import DigitizerInitError

def main():

    print("==============================================")
    print("          H2Laser DAQ System  (v2.0)")
    print("          Developer: Meng Lyu @ Dec. 2025")
    print("          Start time:", datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    print("==============================================\n")
    # Pass macro configs into the classes
    try:
        daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)
    except SystemExit:
        print("[FATAL] DAQ could not start. Program terminated.")
        return
    monitor = H2MonitorApp(channels = ["355", "212", "820", "NO_cell"], update_queue=daq_manager.update_queue)

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

        print("\n==============================================")
        print("        H2Laser DAQ ended normally.")
        print("==============================================")

if __name__ == "__main__":
    main()