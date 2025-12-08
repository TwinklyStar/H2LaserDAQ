# h2_digitizer.py
import threading
import ctypes
from picosdk.ps3000a import ps3000a as ps
import numpy as np
import matplotlib.pyplot as plt
from picosdk.functions import mV2adc, adc2mV, assert_pico_ok
import time
from datetime import datetime
import glob
import os
import csv
import picoDAQAssistant

class H2LaserDigitizer(threading.Thread):
    def __init__(self, name, config, update_queue, stop_event):
        super().__init__(name=name)
        self.config = config           # dict from h2_config.DIGITIZER_CONFIGS[name]
        self.update_queue = update_queue
        self.stop_event = stop_event
        self.trigger_per_file = 10000  # 400 s

        # Example: you can pre-extract some config here
        self.serial = config.get("serial")
        self.model = config.get("model")
        self.data_path = config.get("data_path")
        self.output_name = config.get("output_name")

        # Output initilization
        self.csv_pointer = None
        self.root_pointer = None

        # TODO: init PicoScope handle etc.
        if self.model == "3405D":
            print("Initialize picoscope 3405D")
            self.initPico3000(config)


    def run(self):
        # Main thread loop for this digitizer
        # TODO: connect + configure digitizer here once
        # self._connect_to_digitizer()

        while not self.stop_event.is_set():
            # TODO: acquire waveform, compute integrated area
            date = datetime.today().strftime("%y%m%d")

            # Create ROOT file
            today_root_number = len(glob.glob("{}/root/{}_{}*.root".format(self.data_path, self.output_name, date)))
            root_name = "{}/root/{}_{}_{:04d}.root".format(self.data_path, self.output_name, date, today_root_number)

            self.root_pointer = picoDAQAssistant.RootManager(filename=root_name, runN=0, chunk_size=1000, sample_num=self.sample_number, add_channels=self.channels)
            self.root_pointer.start_thread()

            # Create csv file
            csv_fullpath = f"{self.data_path}/csv/{date}.csv"
            file_exists = os.path.exists(csv_fullpath)

            if self.csv_pointer is not None:    # Create new file
                self.csv_pointer.close()
            self.csv_pointer = open(csv_fullpath, "a", newline="")
            self.csv_writer = csv.DictWriter(self.csv_pointer, fieldnames=["timestamp"]+self.channels)
            if not file_exists: # Create new file
                self.csv_writer.writeheader()

            trigger_cnt = 0

            time_start = time.time()
            while (trigger_cnt < self.trigger_per_file and not self.stop_event.is_set()):
                if self.model == "3405D":
                    self.pico3000BlockCapture()

                wave = {"Time": self.t}
                for ch_idx in self.channels:
                    wave[f"Ch{ch_idx}"] = picoDAQAssistant.fastAdc2mV(self.bufferMax[ch_idx], self.ch_range[ch_idx], self.maxADC, self.ch_offset[ch_idx])

                self.root_pointer.fill(**wave)

                if (trigger_cnt % 1000 == 0):
                    csv_row = {}
                    csv_row['timestamp'] = time.time()
                    for ch_idx in self.channels:
                        csv_row[ch_idx] = np.sum(wave[f"Ch{ch_idx}"]) * self.delta_t
                    self.csv_writer.writerow(csv_row)
                    self.csv_pointer.flush()
                    # Send latest value to monitor
                    # self.update_queue.put({
                    #     "device": self.name,
                    #     "timestamp": timestamp,
                    #     "value": value,
                    # })

                trigger_cnt += 1

                if (trigger_cnt % 1000 == 0):
                    time_elapsed = time.time()-time_start
                    print(f"Triggered 1000 events, takes {time_elapsed} s")
                    time_start = time.time()

            self.root_pointer.close()
    
    def close(self):
        self.csv_pointer.close()

        # Stops the scope
        # Handle = chandle
        self.status["stop"] = ps.ps3000aStop(self.chandle)
        assert_pico_ok(self.status["stop"])

        # Closes the unit
        # Handle = chandle
        self.status["close"] = ps.ps3000aCloseUnit(self.chandle)
        assert_pico_ok(self.status["close"])

    def initPico3000(self, config):
        # Create chandle and self.status ready for use
        self.status = {}
        self.chandle = ctypes.c_int16()

        # Opens the device/s
        self.status["openunit"] = ps.ps3000aOpenUnit(ctypes.byref(self.chandle), None)

        try:
            assert_pico_ok(self.status["openunit"])
        except:

            # powerstate becomes the self.status number of openunit
            powerstate = self.status["openunit"]

            # If powerstate is the same as 282 then it will run this if statement
            if powerstate == 282:
                # Changes the power input to "PICO_POWER_SUPPLY_NOT_CONNECTED"
                self.status["ChangePowerSource"] = ps.ps3000aChangePowerSource(self.chandle, 282)
                # If the powerstate is the same as 286 then it will run this if statement
            elif powerstate == 286:
                # Changes the power input to "PICO_USB3_0_DEVICE_NON_USB3_0_PORT"
                self.status["ChangePowerSource"] = ps.ps3000aChangePowerSource(self.chandle, 286)
            else:
                raise

            assert_pico_ok(self.status["ChangePowerSource"])

        self.channels = config.get("channels")
        self.unused_channels = set(["A", "B", "C", "D"]) - set(self.channels)

        self.ch_range = {}
        self.ch_offset = {}
        for ch_idx in self.channels:
            channel_No = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
            self.ch_range[ch_idx] = ps.PS3000A_RANGE["PS3000A_"+config.get("voltage_range")[ch_idx]]
            coupling = ps.PS3000A_COUPLING["PS3000A_DC"]
            enabled = 1  # off: 0, on: 1
            self.ch_offset[ch_idx] = config.get("offset")[ch_idx] # in V
            self.status["setCh"+ch_idx] = ps.ps3000aSetChannel(self.chandle, channel_No, enabled, coupling, self.ch_range[ch_idx], self.ch_offset[ch_idx])
            assert_pico_ok(self.status["setCh"+ch_idx])

        for ch_idx in self.unused_channels:     # Disable unused channels
            channel_No = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
            range = ps.PS3000A_RANGE["PS3000A_2V"]
            coupling = ps.PS3000A_COUPLING["PS3000A_DC"]
            enabled = 0  # off: 0, on: 1
            analog_offset = 0
            self.status["setCh"+ch_idx] = ps.ps3000aSetChannel(self.chandle, channel_No, enabled, coupling, range, analog_offset)
            assert_pico_ok(self.status["setCh"+ch_idx])


        # Sets up single trigger
        trigger_enable = 1  # 0 to disable, any other number to enable
        trigger_channel = config.get("trigger_channel")
        if trigger_channel == "Ext":
            trig_ch_handle = ps.PS3000A_CHANNEL["PS3000A_EXTERNAL"]
        else:
            trig_ch_handle = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_"+trigger_channel]

        trigger_level_mV = config.get("trigger_level")
        trigger_level_ADC = picoDAQAssistant.extTrigmV2Adc(trigger_level_mV)
        # Finds the max ADC count
        # Handle = self.chandle
        # Value = ctype.byref(maxADC)
        self.maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps3000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
        # assert_pico_ok(self.status["maximumValue"])
        # trigger_level_ADC = mV2adc(trigger_level_mV, chA_range, maxADC)

        # trigger_type = ps.PS3000A_THRESHOLD_DIRECTION["PS3000A_RISING"]
        trigger_type = ps.PS3000A_THRESHOLD_DIRECTION["PS3000A_"+config.get("trigger_edge")]
        trigger_delay = config.get("trigger_delay")   # Number of sample
        auto_trigger = config.get("auto_trigger") # autotrigger wait time (in ms)
        # self.status["trigger"] = ps.ps3000aSetSimpleTrigger(self.chandle, trigger_enable, chA_channel_No, trigger_level_ADC, trigger_type, trigger_delay, auto_trigger)
        self.status["trigger"] = ps.ps3000aSetSimpleTrigger(self.chandle, trigger_enable, trig_ch_handle, trigger_level_ADC, trigger_type, trigger_delay, auto_trigger)
        assert_pico_ok(self.status["trigger"])

        # Setting the number of sample to be collected
        self.sample_number = config.get("sample_number")
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
        self.status["GetTimebase"] = ps.ps3000aGetTimebase2(self.chandle, self.timebase, maxsamples, ctypes.byref(timeIntervalns), 1, ctypes.byref(returnedMaxSamples), 0)
        assert_pico_ok(self.status["GetTimebase"])

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
        i=0
        for ch_idx in self.channels:
            self.status["SetDataBuffers"] = ps.ps3000aSetDataBuffers(self.chandle, ps.PS3000A_CHANNEL["PS3000A_CHANNEL_"+ch_idx]
, self.bufferMax[ch_idx].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), self.bufferMin[ch_idx].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), maxsamples, 0, 0)
        assert_pico_ok(self.status["SetDataBuffers"])

        # Creates a overlow location for data
        self.overflow = (ctypes.c_int16 * 10)()

        # Creates the time data
        self.t = np.linspace(0, (self.cmaxSamples.value - 1) * timeIntervalns.value, self.cmaxSamples.value)
        self.delta_t = timeIntervalns.value

    # def initPico2000():

    def pico3000BlockCapture(self):
        # Starts the block capture
        self.status["runblock"] = ps.ps3000aRunBlock(self.chandle, self.preTriggerSamples, self.postTriggerSamples, self.timebase, 1, None, 0, None, None)
        assert_pico_ok(self.status["runblock"])


        # Checks data collection to finish the capture
        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        self.status["isReady"] = ps.ps3000aIsReady(self.chandle, ctypes.byref(ready))
        while ready.value == check.value:
            time.sleep(0.01)
            self.status["isReady"] = ps.ps3000aIsReady(self.chandle, ctypes.byref(ready))

        self.status["GetValues"] = ps.ps3000aGetValues(self.chandle, 0, ctypes.byref(self.cmaxSamples), 0, 0, 0, ctypes.byref(self.overflow))
        assert_pico_ok(self.status["GetValues"])
