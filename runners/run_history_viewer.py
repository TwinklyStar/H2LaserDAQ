from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def main(history_config: dict) -> None:
    try:
        start_time = datetime.strptime(
            history_config["start_time"], "%Y-%m-%d %H:%M:%S"
        )
        end_time = datetime.strptime(
            history_config["end_time"], "%Y-%m-%d %H:%M:%S"
        )
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid history config: {e}") from e

    start_ts     = start_time.timestamp()
    end_ts       = end_time.timestamp()
    channel_name = history_config["channel_name"]
    run_name     = history_config["run_name"]
    data_path    = history_config["data_path"]

    time_itr = start_time
    t        = []
    val      = []

    while time_itr.date() <= end_time.date():
        path = f'{data_path}{run_name}_{time_itr.strftime("%y%m%d")}.csv'
        df   = pd.read_csv(path)
        if "timestamp" not in df.columns or channel_name not in df.columns:
            raise RuntimeError(f"{path}: missing required column")

        df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["time"] = df["time"].dt.tz_convert("Asia/Tokyo")
        mask       = (df["timestamp"] > start_ts) & (df["timestamp"] < end_ts)

        t.extend(df.loc[mask, "time"].to_list())
        val.extend(df.loc[mask, channel_name].to_numpy())
        time_itr += timedelta(days=1)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, val)
    ax.set_xlabel("Time [JST]")
    ax.set_ylabel(r"Integrated area [nV·s]")
    ax.set_title(channel_name)
    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%y-%m-%d %H:%M:%S", tz=ZoneInfo("Asia/Tokyo"))
    )
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    fig.tight_layout()
    plt.show()
