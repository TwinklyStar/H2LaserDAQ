from config_history import HISTORY_CONFIG
import os
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def main():
    try:
        start_time = datetime.strptime(HISTORY_CONFIG.get("start_time"), "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(HISTORY_CONFIG.get("end_time"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise
    channel_name = HISTORY_CONFIG.get("channel_name")
    run_name = HISTORY_CONFIG.get("run_name")
    time_itr = start_time
    t = []
    val = []
    while time_itr.date() <= end_time.date():
        try:
            path = f'data/csv/{run_name}_{time_itr.strftime("%y%m%d")}.csv'
        except FileNotFoundError:
            raise
        df = pd.read_csv(path)
        if "timestamp" not in df.columns and channel_name not in df.columns:
            raise RuntimeError(f"{path}: missing required column")
        t.extend(pd.to_datetime(df['timestamp'], unit='s'))
        val.extend(df[channel_name].to_numpy())

        time_itr = time_itr + timedelta(days=1)
    
    fig, ax = plt.subplots(figsize=(10,4))

    ax.plot(t, val)
    ax.set_xlabel("Time")
    ax.set_ylabel(r"Integrated area [mV$\times$ns]")
    ax.set_title(channel_name)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y-%m-%d %H:%M:%S'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    fig.tight_layout()

    plt.show()



if __name__ == "__main__":
    main()


    