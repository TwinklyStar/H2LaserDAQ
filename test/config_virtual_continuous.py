# config_virtual_continuous.py
# Configuration for the virtual continuous-mode DAQ test.
# Two channels are simulated: "355" and "212".

VIRTUAL_CONFIGS = {
    "VirtualDET": {
        "run_mode": "continuous",
        "channels": ["A", "B"],
        "channel_name": ["355", "212"],
        "voltage_range": {"A": "2V", "B": "2V", "C": "2V", "D": "2V"},

        # Sampling: 1000 samples × 10 ns = 10 µs total window
        "sample_number": 1000,
        "delta_t": 10,          # ns per sample

        # Trigger: 10 % pre-trigger → pulse starts at sample 100
        "pre_trigger": 10,

        "output_name": "virtual_continuous",
        "data_path": "data",
    },
}
