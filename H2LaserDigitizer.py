# h2_digitizer.py
import threading
import ctypes
from picosdk.ps3000a import ps3000a
from picosdk.ps2000 import ps2000
import numpy as np
import matplotlib.pyplot as plt
from picosdk.functions import mV2adc, adc2mV, assert_pico_ok, assert_pico2000_ok
import time
from datetime import datetime
import glob
import os
import csv
import picoDAQAssistant
from H2Exceptions import DigitizerInitError
from utility import log

class H2LaserDigitizer(threading.Thread):
    def __init__(self, name, config, update_queue, stop_event):
        super().__init__(name=name)
        self.config = config           # dict from h2_config.DIGITIZER_CONFIGS[name]
        self.update_queue = update_queue
        self.stop_event = stop_event
        self.trigger_per_file = 10000  # 400 s

        # Example: you can pre-extract some config here
        self.run_mode = config.get("run_mode")
        self.serial = config.get("serial")
        self.model = config.get("model")
        self.data_path = config.get("data_path")
        self.output_name = config.get("output_name")
        self.channel_name = {}
        self.channels = config.get("channels")
        print(f"[INIT] Initializing digitizer {self.model} {self.serial}")

        for i in range(len(self.channels)):
            self.channel_name[self.channels[i]] = config.get("channel_name")[i]

        # Output initilization
        self.csv_pointer = None
        self.root_pointer = None

        # TODO: init PicoScope handle etc.
        try:
            if self.model == "3405D":
                self.initPico3000(config)
            elif self.model == "2204A":
                self.initPico2000(config)
        except DigitizerInitError:
            raise

        if self.run_mode == "continuous":
            self.peak_area_buffer = {ch : 0 for ch in self.channels}
            self.avg_wave_buffer = {ch: np.zeros(self.sample_number) for ch in self.channels}

        if self.run_mode == "snapshot":
            self.snapshot_channel = config.get("snapshot_channel")
            self.refresh_trigger_cnt = config.get("refresh_trigger_cnt")
            self.peak_area_buffer = []
            self.avg_wave_buffer = {ch: np.zeros(self.sample_number) for ch in self.channels}



    def run(self):
        # Main thread loop for this digitizer
        # TODO: connect + configure digitizer here once
        # self._connect_to_digitizer()

        date_past = ""
        while not self.stop_event.is_set():
            # TODO: acquire waveform, compute integrated area
            date = datetime.today().strftime("%y%m%d")

            # Create ROOT file
            today_root_number = len(glob.glob("{}/root/{}_{}*.root".format(self.data_path, self.output_name, date)))
            root_name = "{}/root/{}_{}_{:04d}.root".format(self.data_path, self.output_name, date, today_root_number)

            self.root_pointer = picoDAQAssistant.RootManager(filename=root_name, runN=0, chunk_size=1000, sample_num=self.sample_number, add_channels=self.channels)
            self.root_pointer.start_thread()
            print(f"[I/O] Opening ROOT file {root_name}")

            if self.run_mode == "continuous" and date_past != date:
                # Create csv file
                csv_fullpath = f"{self.data_path}/csv/{self.output_name}_{date}.csv"
                file_exists = os.path.exists(csv_fullpath)

                if self.csv_pointer is not None:    # Create new file
                    self.csv_pointer.close()
                    print(f"[I/O] Data saved to CSV file {csv_fullpath}. File closed")
                self.csv_pointer = open(csv_fullpath, "a", newline="")
                print(f"[I/O] Opening CSV file {csv_fullpath}")
                self.csv_writer = csv.DictWriter(self.csv_pointer, fieldnames=["timestamp"]+self.channels)
                if not file_exists: # Create new file
                    self.csv_writer.writeheader()
                date_past = date

            trigger_cnt = 0

            time_start = time.time()
            while (trigger_cnt < self.trigger_per_file and not self.stop_event.is_set()):
                trigger_cnt += 1
                if self.model == "3405D":
                    self.pico3000BlockCapture()
                elif self.model == "2204A":
                    self.pico2000BlockCapture()

                wave = {"Time": self.t}
                for ch_idx in self.channels:
                    wave[f"Ch{ch_idx}"] = picoDAQAssistant.fastAdc2mV(self.bufferMax[ch_idx], self.ch_range[ch_idx], self.maxADC, self.ch_offset[ch_idx])

                self.root_pointer.fill(**wave)

                if (self.run_mode == "continuous"):
                    for ch_idx in self.channels:
                        self.peak_area_buffer[ch_idx] += np.sum(wave[f"Ch{ch_idx}"]) * self.delta_t / 100
                        self.avg_wave_buffer[ch_idx] += wave[f"Ch{ch_idx}"] / 100
                    
                    if (trigger_cnt % 100 == 0):
                        csv_row = {}
                        csv_row['timestamp'] = time.time()
                        for ch_idx in self.channels:
                            csv_row[ch_idx] = self.peak_area_buffer[ch_idx]
                            # Send latest value to monitor
                            queue_dic = {
                                "channel_name": self.channel_name[ch_idx],
                                "timestamp": csv_row['timestamp'],
                                "value": csv_row[ch_idx],
                                "wfm_t": self.t,
                                "wfm": self.avg_wave_buffer[ch_idx].copy()
                            }
                        
                        self.update_queue.put(queue_dic)

                        for ch_idx in self.channels:
                            self.avg_wave_buffer[ch_idx].fill(0)
                            self.peak_area_buffer[ch_idx] = 0
                        
                        self.csv_writer.writerow(csv_row)
                        self.csv_pointer.flush()

                if (self.run_mode == "snapshot"):
                    self.peak_area_buffer.append(np.sum(wave[f"Ch{self.snapshot_channel}"]) * self.delta_t)
                    for ch_idx in self.channels:
                        self.avg_wave_buffer[ch_idx] += wave[f"Ch{ch_idx}"] / self.refresh_trigger_cnt
                    if (trigger_cnt % self.refresh_trigger_cnt == 0):    # Reflesh the plot, show the average peak area during last refresh period
                        area_avg = np.mean(self.peak_area_buffer)
                        area_std = np.std(self.peak_area_buffer)
                        queue_dic = {
                            "device": self.name,
                            "t": self.t,
                            "area_avg": area_avg,
                            "area_std": area_std,
                            "trigger_cnt": self.refresh_trigger_cnt
                        }
                        for ch_idx in self.channels:
                            queue_dic[f"Ch{ch_idx}"] = self.avg_wave_buffer[ch_idx].copy()

                        self.update_queue.put(queue_dic)

                        for ch_idx in self.channels:
                            self.avg_wave_buffer[ch_idx].fill(0)



                if (trigger_cnt % 1000 == 0):
                    time_elapsed = time.time()-time_start
                    print(f'[DAQ] Health: {datetime.now().strftime("%y-%m-%d %H:%M:%S")} Trigger rate {1000 / time_elapsed} Hz')
                    time_start = time.time()

            self.root_pointer.close()
            print(f"[I/O] Data saved to ROOT file {self.root_pointer.getName()}. File closed")
    
    def close(self):
        if self.run_mode == "continuous":
            self.csv_pointer.close()
            print(f"[I/O] Data saved to CSV file {self.csv_pointer.name}. File closed")

        if self.model == "3405D":
            # Stops the scope
            # Handle = chandle
            self.status["stop"] = ps3000a.ps3000aStop(self.chandle)
            assert_pico_ok(self.status["stop"])

            # Closes the unit
            # Handle = chandle
            self.status["close"] = ps3000a.ps3000aCloseUnit(self.chandle)
            assert_pico_ok(self.status["close"])
        if self.model == "2204A":
            self.status["stop"] = ps2000.ps2000_stop(self.chandle)
            assert_pico2000_ok(self.status["stop"])

            # Close unitDisconnect the scope
            # handle = chandle
            self.status["close"] = ps2000.ps2000_close_unit(self.chandle)
            assert_pico2000_ok(self.status["close"])

    def initPico3000(self, config):
        # Create chandle and self.status ready for use
        self.status = {}
        self.chandle = ctypes.c_int16()

        # Opens the device/s
        self.status["openunit"] = ps3000a.ps3000aOpenUnit(ctypes.byref(self.chandle), None)

        try:
            assert_pico_ok(self.status["openunit"])
        except:

            # powerstate becomes the self.status number of openunit
            powerstate = self.status["openunit"]

            # If powerstate is the same as 282 then it will run this if statement
            if powerstate == 282:
                # Changes the power input to "PICO_POWER_SUPPLY_NOT_CONNECTED"
                self.status["ChangePowerSource"] = ps3000a.ps3000aChangePowerSource(self.chandle, 282)
                # If the powerstate is the same as 286 then it will run this if statement
            elif powerstate == 286:
                # Changes the power input to "PICO_USB3_0_DEVICE_NON_USB3_0_PORT"
                self.status["ChangePowerSource"] = ps3000a.ps3000aChangePowerSource(self.chandle, 286)
            else:
                raise DigitizerInitError(f"[ERROR] Specified digitizer {self.model} {self.serial} not found")

            assert_pico_ok(self.status["ChangePowerSource"])
        print(f"[INIT] Specified digitizer {self.model} {self.serial} found")

        # self.channels = config.get("channels")
        self.unused_channels = set(["A", "B", "C", "D"]) - set(self.channels)

        self.ch_range = {}
        self.ch_offset = {}
        print(f"[INIT] Setting channels: {self.channels}")
        for ch_idx in self.channels:
            channel_No = ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
            self.ch_range[ch_idx] = ps3000a.PS3000A_RANGE["PS3000A_"+config.get("voltage_range")[ch_idx]]
            coupling = ps3000a.PS3000A_COUPLING["PS3000A_DC"]
            enabled = 1  # off: 0, on: 1
            self.ch_offset[ch_idx] = config.get("offset")[ch_idx] # in V
            self.status["setCh"+ch_idx] = ps3000a.ps3000aSetChannel(self.chandle, channel_No, enabled, coupling, self.ch_range[ch_idx], self.ch_offset[ch_idx])
            try:
                assert_pico_ok(self.status["setCh"+ch_idx])
            except:
                raise DigitizerInitError(f"[ERROR] Fail to initizlize Channel {ch_idx}")

        for ch_idx in self.unused_channels:     # Disable unused channels
            channel_No = ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
            range = ps3000a.PS3000A_RANGE["PS3000A_2V"]
            coupling = ps3000a.PS3000A_COUPLING["PS3000A_DC"]
            enabled = 0  # off: 0, on: 1
            analog_offset = 0
            self.status["setCh"+ch_idx] = ps3000a.ps3000aSetChannel(self.chandle, channel_No, enabled, coupling, range, analog_offset)
            assert_pico_ok(self.status["setCh"+ch_idx])


        # Sets up single trigger
        print(f"[INIT] Setting trigger")
        trigger_enable = 1  # 0 to disable, any other number to enable
        trigger_channel = config.get("trigger_channel")
        trigger_level_mV = config.get("trigger_level")
        print(f"\tTrigger channel: {trigger_channel}")
        print(f"\tTrigger level {trigger_level_mV} mV")
        if trigger_channel == "Ext":
            trig_ch_handle = ps3000a.PS3000A_CHANNEL["PS3000A_EXTERNAL"]
            trigger_level_ADC = picoDAQAssistant.extTrigmV2Adc(trigger_level_mV)
        else:
            trig_ch_handle = ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_"+trigger_channel]
            maxADC = ctypes.c_int16()
            self.status["maximumValue"] = ps3000a.ps3000aMaximumValue(self.chandle, ctypes.byref(maxADC))
            assert_pico_ok(self.status["maximumValue"])
            trigger_level_ADC = mV2adc(trigger_level_mV, self.ch_range[trigger_channel], maxADC)

        # Finds the max ADC count
        # Handle = self.chandle
        # Value = ctype.byref(maxADC)
        self.maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps3000a.ps3000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
        # assert_pico_ok(self.status["maximumValue"])
        # trigger_level_ADC = mV2adc(trigger_level_mV, chA_range, maxADC)

        # trigger_type = ps3000a.PS3000A_THRESHOLD_DIRECTION["PS3000A_RISING"]
        trigger_type = ps3000a.PS3000A_THRESHOLD_DIRECTION["PS3000A_"+config.get("trigger_edge")]
        print(f"\tTrigger type: {trigger_type}")
        trigger_delay = config.get("trigger_delay")   # Number of sample
        auto_trigger = config.get("auto_trigger") # autotrigger wait time (in ms)
        # self.status["trigger"] = ps3000a.ps3000aSetSimpleTrigger(self.chandle, trigger_enable, chA_channel_No, trigger_level_ADC, trigger_type, trigger_delay, auto_trigger)
        self.status["trigger"] = ps3000a.ps3000aSetSimpleTrigger(self.chandle, trigger_enable, trig_ch_handle, trigger_level_ADC, trigger_type, trigger_delay, auto_trigger)
        try:
            assert_pico_ok(self.status["trigger"])
        except:
            raise DigitizerInitError("[ERROR] Fail to set trigger")

        # Setting the number of sample to be collected
        print(f"[INIT] Setting sampling configuration")
        self.sample_number = config.get("sample_number")
        print(f"\tSample number: {self.sample_number}")
        self.preTriggerSamples = int(config.get("pre_trigger") / 100. * self.sample_number)
        self.postTriggerSamples = self.sample_number - self.preTriggerSamples
        maxsamples = self.sample_number

        # Gets timebase innfomation
        # WARNING: When using this example it may not be possible to access all Timebases as all channels are enabled by default when opening the scope.  
        # To access these Timebases, set any unused analogue channels to off.
        # Handle = self.chandle
        # Timebase = 2 = timebase
        # Nosample = maxsamples
        # TimeIntervalNanoseconds = ctypes.byref(timeIntervalns)
        # MaxSamples = ctypes.byref(returnedMaxSamples)
        # Segement index = 0
        # timebase guide: 
        #   0: 1 ns (only 1 channel enabled)
        #   1: 2 ns
        #   2: 4 ns
        #   n>2: (n-2) * 8 ns
        # timebase = 252  # Sampling interval = (n-2) * 8ns
        # timebase = 22
        self.timebase = config.get("timebase")
        timeIntervalns = ctypes.c_float()
        returnedMaxSamples = ctypes.c_int16()
        self.status["GetTimebase"] = ps3000a.ps3000aGetTimebase2(self.chandle, self.timebase, maxsamples, ctypes.byref(timeIntervalns), 1, ctypes.byref(returnedMaxSamples), 0)
        try:
            assert_pico_ok(self.status["GetTimebase"])
        except:
            raise DigitizerInitError(f"[ERROR] Incorrect timebase {self.timebase}")

        print(f"\tSample interval: {timeIntervalns} ns")

        # Creates a overlow location for data
        overflow = ctypes.c_int16()
        # Creates converted types maxsamples
        self.cmaxSamples = ctypes.c_int32(maxsamples)

        # Create buffers ready for assigning pointers for data collection
        self.bufferMax = {}
        self.bufferMin = {}
        for ch_idx in self.channels:
            self.bufferMax[ch_idx] = np.zeros(shape=maxsamples, dtype=np.int16)
            self.bufferMin[ch_idx] = np.zeros(shape=maxsamples, dtype=np.int16)

        # Setting the data buffer location for data collection from channel A
        for ch_idx in self.channels:
            self.status["SetDataBuffers"] = ps3000a.ps3000aSetDataBuffers(self.chandle, ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
, self.bufferMax[ch_idx].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), self.bufferMin[ch_idx].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), maxsamples, 0, 0)
        try:
            assert_pico_ok(self.status["SetDataBuffers"])
        except:
            raise("[ERROR] Fail to set data buffer")

        # Creates a overlow location for data
        self.overflow = (ctypes.c_int16 * 10)()

        # Creates the time data
        self.t = np.linspace(0, (self.cmaxSamples.value - 1) * timeIntervalns.value, self.cmaxSamples.value)
        self.delta_t = timeIntervalns.value

        print("[INIT] Initialization complete")

    def initPico2000(self, config):
        self.status = {}

        # Open as many 2204A as are connected (call until it returns 0)
        handles = {}
        while True:
            h = ps2000.ps2000_open_unit()
            if h <= 0:  # 0 = none found, -1 = failed
                break
            handles[self.getPico2000Serial(h)] = h
        
        print(f">>> {len(handles)} pico2000 detected")

        # Close unmatched ones
        self.chandle = None
        for serial, handle in handles.items():
            if serial == self.serial:
                self.chandle = ctypes.c_int16(handle)
                print(f"[INIT] Specified digitizer {self.model} {self.serial} found")
            else:
                ps2000.ps2000_close_unit(handle)
        if self.chandle == None:
            raise DigitizerInitError(f"[ERROR] Specified digitizer {self.model} {self.serial} not found")

        # self.channels = config.get("channels")
        self.unused_channels = set(["A", "B"]) - set(self.channels)

        self.ch_range = {}
        self.ch_offset = {"A": 0, "B": 0}
        print(f"[INIT] Setting channels: {self.channels}")
        for ch_idx in self.channels:
            channel_No = ps2000.PS2000_CHANNEL["PS2000_CHANNEL_"+ch_idx]
            self.ch_range[ch_idx] = ps2000.PS2000_VOLTAGE_RANGE["PS2000_"+config.get("voltage_range")[ch_idx]]
            coupling = ps2000.PICO_COUPLING["DC"]
            enabled = 1  # off: 0, on: 1
            self.status["setCh"+ch_idx] = ps2000.ps2000_set_channel(self.chandle, channel_No, enabled, coupling, self.ch_range[ch_idx])
            try:
                assert_pico2000_ok(self.status["setCh"+ch_idx])
            except:
                raise DigitizerInitError(f"[ERROR] Fail to initizlize Channel {ch_idx}")

        for ch_idx in self.unused_channels:     # Disable unused channels
            channel_No = ps2000.PS2000_CHANNEL["PS2000_CHANNEL_"+ch_idx]
            range = ps2000.PS2000_VOLTAGE_RANGE["PS2000_2V"]
            coupling = ps2000.PICO_COUPLING["DC"]
            enabled = 0  # off: 0, on: 1
            self.status["setCh"+ch_idx] = ps2000.ps2000_set_channel(self.chandle, channel_No, enabled, coupling, range)
            assert_pico2000_ok(self.status["setCh"+ch_idx])


        # Sets up single trigger
        print(f"[INIT] Setting trigger")
        trigger_channel = config.get("trigger_channel")
        trig_ch_handle = ps2000.PS2000_CHANNEL["PS2000_CHANNEL_"+trigger_channel]
        print(f"\tTrigger channel: {trigger_channel}")

        trigger_level_mV = config.get("trigger_level")
        print(f"\tTrigger level {trigger_level_mV} mV")
        # find maximum ADC count value
        self.maxADC = ctypes.c_int16(32767)
        trigger_level_ADC = mV2adc(trigger_level_mV, self.ch_range[trigger_channel], self.maxADC)
        # print(trigger_level_ADC)

        pre_trigger = config.get("pre_trigger") * -1

        trigger_type = 0 if config.get("trigger_edge") == "RISING" else 1
        trigger_str = "RISING" if trigger_type == 0 else "FALLING"
        print(f"\tTrigger type: {trigger_str}")

        auto_trigger = config.get("auto_trigger") # autotrigger wait time (in ms)

        self.status["trigger"] = ps2000.ps2000_set_trigger(self.chandle, trig_ch_handle, trigger_level_ADC, trigger_type, pre_trigger, auto_trigger)
        # self.status["trigger"] = ps2000.ps2000_set_trigger(self.chandle, 0, 819, 3, -50, auto_trigger)
        try:
            assert_pico2000_ok(self.status["trigger"])
        except:
            raise DigitizerInitError("[ERROR] Fail to set trigger")


        print(f"[INIT] Setting sampling configuration")
        # Setting the number of sample to be collected
        self.sample_number = config.get("sample_number")
        maxsamples = self.sample_number
        print(f"\tSample number: {self.sample_number}")

        # Gets timebase innfomation
        # Timebase guide for 2204A: 
        # 0 : 10ns   <- Only available in 1-channel mode
        # 1 : 20ns  // half
        # 2 : 40ns  // half
        # 3 : 80ns  // half
        # ...
        self.timebase = config.get("timebase")
        timeInterval = ctypes.c_int32()
        timeUnits = ctypes.c_int32()
        oversample = ctypes.c_int16(1)
        maxSamplesReturn = ctypes.c_int32()
        self.status["getTimebase"] = ps2000.ps2000_get_timebase(self.chandle, self.timebase, maxsamples, ctypes.byref(timeInterval), ctypes.byref(timeUnits), oversample, ctypes.byref(maxSamplesReturn))
        try:
            assert_pico2000_ok(self.status["getTimebase"])
        except:
            raise DigitizerInitError(f"[ERROR] Incorrect timebase {self.timebase}")

        print(f"\tSample interval: {timeInterval} ns")

        # Creates converted types maxsamples
        self.cmaxSamples = ctypes.c_int32(maxsamples)
        self.pico2000_timeIndisposedms = ctypes.c_int32()

        # Create buffers ready for assigning pointers for data collection
        self.bufferMax = {}
        self.bufferMax['A'] = np.zeros(shape=maxsamples, dtype=np.int16)
        self.bufferMax['B'] = np.zeros(shape=maxsamples, dtype=np.int16)

        # Creates the time data
        self.t = np.linspace(0, (self.cmaxSamples.value - 1) * timeInterval.value, self.cmaxSamples.value)
        self.delta_t = timeInterval.value

        print("[INIT] Initialization complete")
    
    def getPico2000Serial(self, handle):
        # PS2000_GET_UNIT_INFO line=4 returns "batch/serial"
        buf = ctypes.create_string_buffer(64)
        ps2000.ps2000_get_unit_info(ctypes.c_int16(handle), buf, ctypes.c_int16(len(buf)), ctypes.c_int16(4))
        return buf.value.decode(errors="ignore")


    def pico3000BlockCapture(self):
        # Starts the block capture
        self.status["runblock"] = ps3000a.ps3000aRunBlock(self.chandle, self.preTriggerSamples, self.postTriggerSamples, self.timebase, 1, None, 0, None, None)
        assert_pico_ok(self.status["runblock"])


        # Checks data collection to finish the capture
        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        self.status["isReady"] = ps3000a.ps3000aIsReady(self.chandle, ctypes.byref(ready))
        trig_timeout = 10
        trig_start = time.time()
        while ready.value == check.value and not self.stop_event.is_set():
            if time.time() - trig_start > trig_timeout:
                print(f"[WARN]: {self.model} {self.serial}: No trigger for {trig_timeout} seconds")
                trig_timeout += 10
            time.sleep(0.01)
            self.status["isReady"] = ps3000a.ps3000aIsReady(self.chandle, ctypes.byref(ready))


        self.status["GetValues"] = ps3000a.ps3000aGetValues(self.chandle, 0, ctypes.byref(self.cmaxSamples), 0, 0, 0, ctypes.byref(self.overflow))
        if not self.stop_event.is_set():
            assert_pico_ok(self.status["GetValues"])
    
    def pico2000BlockCapture(self):
        oversample = ctypes.c_int16(1)
        self.status["runBlock"] = ps2000.ps2000_run_block(self.chandle, self.sample_number, self.timebase, oversample, ctypes.byref(self.pico2000_timeIndisposedms))
        assert_pico2000_ok(self.status["runBlock"])
        # ready = 0

        trig_timeout = 10
        trig_start = time.time()
        while ps2000.ps2000_ready(self.chandle) == 0 and not self.stop_event.is_set():
            if time.time() - trig_start > trig_timeout:
                print(f"[WARN]: {self.model} {self.serial}: No trigger for {trig_timeout} seconds")
                trig_timeout += 10
            time.sleep(0.01)

        self.status["getValues"] = ps2000.ps2000_get_values(self.chandle, self.bufferMax['A'].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), self.bufferMax['B'].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), None, None, ctypes.byref(oversample), self.cmaxSamples)
        assert_pico2000_ok(self.status["getValues"])