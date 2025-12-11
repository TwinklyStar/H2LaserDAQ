DIGITIZER_CONFIGS = {
    "DET10A2": {
        "run_mode": "continuous",   # continuous or snapshot
        "model": "3405D",
        "serial": "JY926/0005",
        "channels": ["A", "B", "C"],
        "channel_name": ["355", "212", "820"],
        "voltage_range": {"A":"2V", "B":"2V", "C":"2V"},      # Check readme
        "offset": {"A":0, "B":0, "C":0},    # V
        "timebase": 2,  # timebase guide (3000 series): 
                        #   0: 1 ns (only 1 channel enabled)
                        #   1: 2 ns (2 channels enabled)
                        #   2: 4 ns
                        #   n>2: (n-2) * 8 ns
        "sample_number": 1000,      # number of points per waveform
        "trigger_channel": "A",     # "A" "B" "C" "D" "Ext"
        "trigger_level": 200,         # mV
        "pre_trigger": 10,          # trigger location in waveform, from 0-100 (%). 0: trigger at first sample, 100: trigger at last sample
        "trigger_edge": "RISING",   # "RISING" or "FALLING"
        "trigger_delay": 0,         # For example, if delay = 100, the scope would wait 100 sample periods before sampling
        "auto_trigger": 0,          # in ms. Waiting time for auto trigger if no trigger comes. 0 means waiting infinitely
        "output_name": "ps3000test01",
        "data_path": "data",
    },
    "NOCell": {
        "run_mode": "continuous",   # continuous or snapshot
        "model": "2204A",
        "serial": "12017/0359",
        "channels": ["A", "B"],
        "channel_name": ["NO_cell", "NO_cell_trig"],
        "voltage_range": {"A":"2V", "B":"2V"},      # Check readme
        "timebase": 1,  # Timebase guide for 2204A: 
                        # 0 : 10ns   <- Only available in 1-channel mode
                        # 1 : 20ns  // half
                        # 2 : 40ns  // half
                        # 3 : 80ns  // half
                        # ...
        "sample_number": 1000,      # number of points per waveform
        "trigger_channel": "A",     # "A" "B"
        "trigger_level": 200,         # mV
        "pre_trigger": 10,          # trigger location in waveform, from 0-100 (%). 0: trigger at first sample, 100: trigger at last sample
        "trigger_edge": "RISING",   # "RISING" or "FALLING"
        # "trigger_edge": "FALLING",   # "RISING" or "FALLING"
        "auto_trigger": 1000,          # in ms. Waiting time for auto trigger if no trigger comes. 0 means waiting infinitely
        "output_name": "ps2000test01",
        "data_path": "data",
    },
}
