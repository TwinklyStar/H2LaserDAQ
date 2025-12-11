DIGITIZER_CONFIGS = {
    "H2PD": {
        "run_mode": "snapshot",     # continuous or snapshot
        "snapshot_channel": "A",    # Only available in snapshot mode
        "refresh_trigger_cnt": 100, # Only available in snapshot mode
        "model": "2204A",
        "serial": "12017/0366",
        "channels": ["A", "B"],
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
        "output_name": "H2PD_test01",
        "data_path": "data",
    }
}
