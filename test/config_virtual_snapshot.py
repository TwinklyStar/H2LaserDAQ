# config_virtual_snapshot.py
# Configuration for the virtual snapshot-mode DAQ test.
# One signal channel ("Sig") plus one trigger channel ("Trig") are simulated.

VIRTUAL_CONFIGS = {
    "VirtualPD": {
        "run_mode": "snapshot",
        "snapshot_channel": "A",        # channel used for peak-area statistics
        "refresh_trigger_cnt": 100,     # average and plot every N triggers

        "channels": ["A", "B"],
        "channel_name": ["Sig", "Trig"],
        "voltage_range": {"A": "2V", "B": "2V"},

        # Sampling: 1000 samples × 10 ns = 10 µs total window
        "sample_number": 1000,
        "delta_t": 10,          # ns per sample

        # Trigger: 10 % pre-trigger → pulse starts at sample 100
        "pre_trigger": 10,

        "output_name": "virtual_snapshot",
        "data_path": "data",
    },
}
