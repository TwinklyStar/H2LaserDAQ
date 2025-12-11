from config_LaserRoomPD import DIGITIZER_CONFIGS
from H2LaserDAQManager import H2LaserDAQManager
from H2LaserMonitorApp import H2MonitorApp
import time
import matplotlib.pyplot as plt
import queue
import numpy as np

def main():
    # Pass macro configs into the classes
    daq_manager = H2LaserDAQManager(DIGITIZER_CONFIGS)
    # monitor = H2MonitorApp(MONITOR_CONFIG, daq_manager.update_queue)

    daq_manager.start_all()

    # try:
    #     # This will be your monitor GUI main loop eventually
    #     monitor.run()

    # Create the canvas for snapshot mode
    fig, ax = plt.subplots()
    ax.set_xlim(0, 5000)    # in ns
    ax.set_ylim(-2000, 2000)# in mV
    ax.set_title("Laser room VUV Photodiode snapshot")

    lineA, = ax.plot([], [], label="ChA")
    lineB, = ax.plot([], [], label="ChB")
    info_text = ax.text(0.02, 0.95, "", transform=ax.transAxes,
                        va="top", ha="left", fontsize=10,
                        bbox=dict(boxstyle="round", fc="white", alpha=0.8))

    plt.ion()      # << turn on interactive mode
    plt.show()

    try:
        while True:
            try:
                # non-blocking-ish: timeout keeps GUI responsive
                data_pack = daq_manager.update_queue.get(timeout=0.05)
                t = data_pack.get("t")
                chA = data_pack.get("ChA")
                chB = data_pack.get("ChB")
                area_avg = data_pack.get("area_avg")
                area_std = data_pack.get("area_std")
                trig = data_pack.get("trigger_cnt")
            except queue.Empty:
                plt.pause(0.5)   # let GUI process events
                continue
            # print(t)
            # print(chA)
            # print(chB)
            lineA.set_data(t, chA)
            lineB.set_data(t, chB)

            info_text.set_text(
                f"Avg peak area (last 4 s):\n"
                "{:.2f} +- {:.2f} mV * ns".format(area_avg, area_std / np.sqrt(trig))
            )

            fig.canvas.draw()
            fig.canvas.flush_events()   # << necessary for instant update
    finally:
        # On exit (or error), stop all digitizer threads cleanly
        daq_manager.stop_all()
        plt.close('all')
        print("Main loop exited, cleanup done.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Interrupted by user, exited")