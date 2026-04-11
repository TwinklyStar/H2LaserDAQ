# H2LaserDigitizer.py
import threading
import ctypes
import numpy as np
import time
from datetime import datetime
import glob
import os
import csv
from . import picoDAQAssistant
from .H2Exceptions import DigitizerInitError
from .utility import log

# picosdk imports are intentionally deferred to the hardware methods below
# (initPico3000, initPico2000, pico3000BlockCapture, pico2000BlockCapture,
#  _close_hardware) so that this module can be imported and subclassed in
#  environments where picosdk is not available (e.g. virtual tests).


class H2LaserDigitizer(threading.Thread):
    def __init__(self, name, config, update_queue, stop_event):
        super().__init__(name=name)
        self.config       = config
        self.update_queue = update_queue
        self.stop_event   = stop_event
        self.trigger_per_file = 10000   # ~400 s at 25 Hz

        self.run_mode    = config.get("run_mode")
        self.serial      = config.get("serial")
        self.model       = config.get("model")
        self.data_path   = config.get("data_path")
        self.output_name = config.get("output_name")
        self.channels    = config.get("channels")

        self.channel_name = {
            self.channels[i]: config.get("channel_name")[i]
            for i in range(len(self.channels))
        }

        self.csv_pointer  = None
        self.root_pointer = None

        try:
            self._init_hardware(config)
        except DigitizerInitError:
            raise

        if self.run_mode == "continuous":
            self.peak_area_buffer = {ch: 0 for ch in self.channels}
            self.avg_wave_buffer  = {ch: np.zeros(self.sample_number)
                                     for ch in self.channels}

        if self.run_mode == "snapshot":
            self.snapshot_channel    = config.get("snapshot_channel")
            self.refresh_trigger_cnt = config.get("refresh_trigger_cnt")
            self.peak_area_buffer    = []
            self.avg_wave_buffer     = {ch: np.zeros(self.sample_number)
                                        for ch in self.channels}

    # -------------------------------------------------------------------------
    # Hardware hooks — override these three methods in subclasses
    # -------------------------------------------------------------------------

    def _init_hardware(self, config):
        """
        Initialise the physical digitizer.
        Must set at minimum: self.sample_number, self.t, self.delta_t,
        self.bufferMax, self.maxADC, self.ch_range, self.ch_offset.
        Override in subclasses to replace hardware with a virtual source.
        """
        if self.model == "3405D":
            self.initPico3000(config)
        elif self.model == "2204A":
            self.initPico2000(config)

    def _capture_block(self):
        """
        Block until one trigger's worth of data is in self.bufferMax.
        Override in subclasses to generate synthetic waveforms instead.
        """
        if self.model == "3405D":
            self.pico3000BlockCapture()
        elif self.model == "2204A":
            self.pico2000BlockCapture()

    def _close_hardware(self):
        """
        Stop and disconnect the physical digitizer.
        Override in subclasses to make this a no-op for virtual sources.
        """
        if self.model == "3405D":
            from picosdk.ps3000a import ps3000a
            from picosdk.functions import assert_pico_ok
            self.status["stop"]  = ps3000a.ps3000aStop(self.chandle)
            assert_pico_ok(self.status["stop"])
            self.status["close"] = ps3000a.ps3000aCloseUnit(self.chandle)
            assert_pico_ok(self.status["close"])

        elif self.model == "2204A":
            from picosdk.ps2000 import ps2000
            from picosdk.functions import assert_pico2000_ok
            self.status["stop"]  = ps2000.ps2000_stop(self.chandle)
            assert_pico2000_ok(self.status["stop"])
            self.status["close"] = ps2000.ps2000_close_unit(self.chandle)
            assert_pico2000_ok(self.status["close"])

    # -------------------------------------------------------------------------
    # Main acquisition loop — shared by real and virtual subclasses
    # -------------------------------------------------------------------------

    def run(self):
        date_past = ""
        while not self.stop_event.is_set():
            date = datetime.today().strftime("%y%m%d")

            # -- open ROOT file -----------------------------------------------
            today_root_number = len(
                glob.glob("{}/root/{}_{}*.root".format(
                    self.data_path, self.output_name, date))
            )
            root_name = "{}/root/{}_{}_{:04d}.root".format(
                self.data_path, self.output_name, date, today_root_number
            )
            self.root_pointer = picoDAQAssistant.RootManager(
                filename=root_name, runN=0, chunk_size=1000,
                sample_num=self.sample_number, add_channels=self.channels,
            )
            self.root_pointer.start_thread()
            print(f"[I/O] Opening ROOT file {root_name}")

            # -- open CSV file (continuous mode, daily rotation) --------------
            if self.run_mode == "continuous" and date_past != date:
                csv_fullpath = (
                    f"{self.data_path}/csv/{self.output_name}_{date}.csv"
                )
                file_exists = os.path.exists(csv_fullpath)
                if self.csv_pointer is not None:
                    self.csv_pointer.close()
                    print(f"[I/O] Data saved to CSV file "
                          f"{self.csv_pointer.name}. File closed")
                self.csv_pointer = open(csv_fullpath, "a", newline="")
                print(f"[I/O] Opening CSV file {csv_fullpath}")
                self.csv_writer = csv.DictWriter(
                    self.csv_pointer,
                    fieldnames=["timestamp"] + list(self.channel_name.values()),
                )
                if not file_exists:
                    self.csv_writer.writeheader()
                date_past = date

            # -- inner trigger loop -------------------------------------------
            trigger_cnt = 0
            time_start  = time.time()

            while (trigger_cnt < self.trigger_per_file
                   and not self.stop_event.is_set()):

                trigger_cnt += 1
                self._capture_block()   # <-- hardware or virtual

                wave = {"Time": self.t}
                for ch_idx in self.channels:
                    wave[f"Ch{ch_idx}"] = picoDAQAssistant.fastAdc2mV(
                        self.bufferMax[ch_idx],
                        self.ch_range[ch_idx],
                        self.maxADC,
                        self.ch_offset[ch_idx],
                    )

                self.root_pointer.fill(**wave)

                # -- continuous mode ------------------------------------------
                if self.run_mode == "continuous":
                    for ch_idx in self.channels:
                        self.peak_area_buffer[ch_idx] += (
                            np.sum(wave[f"Ch{ch_idx}"]) * self.delta_t / 100
                        )
                        self.avg_wave_buffer[ch_idx] += (
                            wave[f"Ch{ch_idx}"] / 100
                        )

                    if trigger_cnt % 100 == 0:
                        csv_row = {"timestamp": time.time()}
                        for ch_idx in self.channels:
                            csv_row[self.channel_name[ch_idx]] = (
                                self.peak_area_buffer[ch_idx]
                            )
                            self.update_queue.put({
                                "channel_name": self.channel_name[ch_idx],
                                "timestamp":    csv_row["timestamp"],
                                "value":        csv_row[self.channel_name[ch_idx]],
                                "wfm_t":        self.t,
                                "wfm":          self.avg_wave_buffer[ch_idx].copy(),
                            })
                        for ch_idx in self.channels:
                            self.avg_wave_buffer[ch_idx].fill(0)
                            self.peak_area_buffer[ch_idx] = 0
                        self.csv_writer.writerow(csv_row)
                        self.csv_pointer.flush()

                # -- snapshot mode --------------------------------------------
                elif self.run_mode == "snapshot":
                    self.peak_area_buffer.append(
                        np.sum(wave[f"Ch{self.snapshot_channel}"])
                        * self.delta_t
                    )
                    for ch_idx in self.channels:
                        self.avg_wave_buffer[ch_idx] += (
                            wave[f"Ch{ch_idx}"] / self.refresh_trigger_cnt
                        )
                    if trigger_cnt % self.refresh_trigger_cnt == 0:
                        area_avg = np.mean(self.peak_area_buffer)
                        area_std = np.std(self.peak_area_buffer)
                        queue_dic = {
                            "device":      self.name,
                            "t":           self.t,
                            "area_avg":    area_avg,
                            "area_std":    area_std,
                            "trigger_cnt": self.refresh_trigger_cnt,
                        }
                        for ch_idx in self.channels:
                            queue_dic[f"Ch{ch_idx}"] = (
                                self.avg_wave_buffer[ch_idx].copy()
                            )
                        self.update_queue.put(queue_dic)
                        for ch_idx in self.channels:
                            self.avg_wave_buffer[ch_idx].fill(0)

                # -- periodic health print ------------------------------------
                if trigger_cnt % 1000 == 0:
                    elapsed = time.time() - time_start
                    print(
                        f"[DAQ] Health: "
                        f"{datetime.now().strftime('%y-%m-%d %H:%M:%S')} "
                        f"Trigger rate {1000 / elapsed:.2f} Hz"
                    )
                    time_start = time.time()

            # -- close ROOT file ----------------------------------------------
            self.root_pointer.close()
            print(f"[I/O] Data saved to ROOT file "
                  f"{self.root_pointer.getName()}. File closed")

    def close(self):
        if self.run_mode == "continuous" and self.csv_pointer is not None:
            self.csv_pointer.close()
            print(f"[I/O] Data saved to CSV file "
                  f"{self.csv_pointer.name}. File closed")
        self._close_hardware()

    # -------------------------------------------------------------------------
    # PicoScope 3405D (PS3000A) — hardware implementation
    # -------------------------------------------------------------------------

    def initPico3000(self, config):
        from picosdk.ps3000a import ps3000a
        from picosdk.functions import mV2adc, assert_pico_ok

        self.status  = {}
        self.chandle = ctypes.c_int16()

        self.status["openunit"] = ps3000a.ps3000aOpenUnit(
            ctypes.byref(self.chandle), None
        )
        try:
            assert_pico_ok(self.status["openunit"])
        except:
            powerstate = self.status["openunit"]
            if powerstate == 282:
                self.status["ChangePowerSource"] = (
                    ps3000a.ps3000aChangePowerSource(self.chandle, 282)
                )
            elif powerstate == 286:
                self.status["ChangePowerSource"] = (
                    ps3000a.ps3000aChangePowerSource(self.chandle, 286)
                )
            else:
                raise DigitizerInitError(
                    f"[ERROR] Specified digitizer {self.model} "
                    f"{self.serial} not found"
                )
            assert_pico_ok(self.status["ChangePowerSource"])
        print(f"[INIT] Specified digitizer {self.model} {self.serial} found")

        self.unused_channels = set(["A", "B", "C", "D"]) - set(self.channels)

        self.ch_range  = {}
        self.ch_offset = {}
        print(f"[INIT] Setting channels: {self.channels}")
        for ch_idx in self.channels:
            channel_No = ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_" + ch_idx]
            self.ch_range[ch_idx]  = ps3000a.PS3000A_RANGE[
                "PS3000A_" + config.get("voltage_range")[ch_idx]
            ]
            coupling = ps3000a.PS3000A_COUPLING["PS3000A_DC"]
            enabled  = 1
            self.ch_offset[ch_idx] = config.get("offset")[ch_idx]
            self.status["setCh" + ch_idx] = ps3000a.ps3000aSetChannel(
                self.chandle, channel_No, enabled, coupling,
                self.ch_range[ch_idx], self.ch_offset[ch_idx],
            )
            try:
                assert_pico_ok(self.status["setCh" + ch_idx])
            except:
                raise DigitizerInitError(
                    f"[ERROR] Fail to initizlize Channel {ch_idx}"
                )

        for ch_idx in self.unused_channels:
            channel_No   = ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_" + ch_idx]
            range_       = ps3000a.PS3000A_RANGE["PS3000A_2V"]
            coupling     = ps3000a.PS3000A_COUPLING["PS3000A_DC"]
            enabled      = 0
            analog_offset = 0
            self.status["setCh" + ch_idx] = ps3000a.ps3000aSetChannel(
                self.chandle, channel_No, enabled, coupling,
                range_, analog_offset,
            )
            assert_pico_ok(self.status["setCh" + ch_idx])

        print(f"[INIT] Setting trigger")
        trigger_enable   = 1
        trigger_channel  = config.get("trigger_channel")
        trigger_level_mV = config.get("trigger_level")
        print(f"\tTrigger channel: {trigger_channel}")
        print(f"\tTrigger level {trigger_level_mV} mV")

        if trigger_channel == "Ext":
            trig_ch_handle    = ps3000a.PS3000A_CHANNEL["PS3000A_EXTERNAL"]
            trigger_level_ADC = picoDAQAssistant.extTrigmV2Adc(trigger_level_mV)
        else:
            trig_ch_handle = ps3000a.PS3000A_CHANNEL[
                "PS3000A_CHANNEL_" + trigger_channel
            ]
            maxADC = ctypes.c_int16()
            self.status["maximumValue"] = ps3000a.ps3000aMaximumValue(
                self.chandle, ctypes.byref(maxADC)
            )
            assert_pico_ok(self.status["maximumValue"])
            trigger_level_ADC = mV2adc(
                trigger_level_mV, self.ch_range[trigger_channel], maxADC
            )

        self.maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps3000a.ps3000aMaximumValue(
            self.chandle, ctypes.byref(self.maxADC)
        )

        trigger_type  = ps3000a.PS3000A_THRESHOLD_DIRECTION[
            "PS3000A_" + config.get("trigger_edge")
        ]
        print(f"\tTrigger type: {trigger_type}")
        trigger_delay = config.get("trigger_delay")
        auto_trigger  = config.get("auto_trigger")

        self.status["trigger"] = ps3000a.ps3000aSetSimpleTrigger(
            self.chandle, trigger_enable, trig_ch_handle,
            trigger_level_ADC, trigger_type, trigger_delay, auto_trigger,
        )
        try:
            assert_pico_ok(self.status["trigger"])
        except:
            raise DigitizerInitError("[ERROR] Fail to set trigger")

        print(f"[INIT] Setting sampling configuration")
        self.sample_number      = config.get("sample_number")
        self.preTriggerSamples  = int(
            config.get("pre_trigger") / 100.0 * self.sample_number
        )
        self.postTriggerSamples = self.sample_number - self.preTriggerSamples
        maxsamples              = self.sample_number
        print(f"\tSample number: {self.sample_number}")

        self.timebase        = config.get("timebase")
        timeIntervalns       = ctypes.c_float()
        returnedMaxSamples   = ctypes.c_int16()
        self.status["GetTimebase"] = ps3000a.ps3000aGetTimebase2(
            self.chandle, self.timebase, maxsamples,
            ctypes.byref(timeIntervalns), 1,
            ctypes.byref(returnedMaxSamples), 0,
        )
        try:
            assert_pico_ok(self.status["GetTimebase"])
        except:
            raise DigitizerInitError(
                f"[ERROR] Incorrect timebase {self.timebase}"
            )
        print(f"\tSample interval: {timeIntervalns.value} ns")

        self.cmaxSamples = ctypes.c_int32(maxsamples)
        self.bufferMax   = {}
        self.bufferMin   = {}
        for ch_idx in self.channels:
            self.bufferMax[ch_idx] = np.zeros(maxsamples, dtype=np.int16)
            self.bufferMin[ch_idx] = np.zeros(maxsamples, dtype=np.int16)

        for ch_idx in self.channels:
            self.status["SetDataBuffers"] = ps3000a.ps3000aSetDataBuffers(
                self.chandle,
                ps3000a.PS3000A_CHANNEL["PS3000A_CHANNEL_" + ch_idx],
                self.bufferMax[ch_idx].ctypes.data_as(
                    ctypes.POINTER(ctypes.c_int16)
                ),
                self.bufferMin[ch_idx].ctypes.data_as(
                    ctypes.POINTER(ctypes.c_int16)
                ),
                maxsamples, 0, 0,
            )
        try:
            assert_pico_ok(self.status["SetDataBuffers"])
        except:
            raise DigitizerInitError("[ERROR] Fail to set data buffer")

        self.overflow = (ctypes.c_int16 * 10)()
        self.t        = np.linspace(
            0,
            (self.cmaxSamples.value - 1) * timeIntervalns.value,
            self.cmaxSamples.value,
        )
        self.delta_t  = timeIntervalns.value
        print("[INIT] Initialization complete")

    def pico3000BlockCapture(self):
        from picosdk.ps3000a import ps3000a
        from picosdk.functions import assert_pico_ok

        self.status["runblock"] = ps3000a.ps3000aRunBlock(
            self.chandle, self.preTriggerSamples, self.postTriggerSamples,
            self.timebase, 1, None, 0, None, None,
        )
        assert_pico_ok(self.status["runblock"])

        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        self.status["isReady"] = ps3000a.ps3000aIsReady(
            self.chandle, ctypes.byref(ready)
        )
        trig_timeout = 10
        trig_start   = time.time()
        while ready.value == check.value and not self.stop_event.is_set():
            if time.time() - trig_start > trig_timeout:
                print(
                    f"[WARN]: {self.model} {self.serial}: "
                    f"No trigger for {trig_timeout} seconds"
                )
                trig_timeout += 10
            time.sleep(0.01)
            self.status["isReady"] = ps3000a.ps3000aIsReady(
                self.chandle, ctypes.byref(ready)
            )

        self.status["GetValues"] = ps3000a.ps3000aGetValues(
            self.chandle, 0, ctypes.byref(self.cmaxSamples),
            0, 0, 0, ctypes.byref(self.overflow),
        )
        if not self.stop_event.is_set():
            assert_pico_ok(self.status["GetValues"])

    # -------------------------------------------------------------------------
    # PicoScope 2204A (PS2000) — hardware implementation
    # -------------------------------------------------------------------------

    def initPico2000(self, config):
        from picosdk.ps2000 import ps2000
        from picosdk.functions import mV2adc, assert_pico2000_ok

        self.status = {}

        handles = {}
        while True:
            h = ps2000.ps2000_open_unit()
            if h <= 0:
                break
            handles[self.getPico2000Serial(h)] = h
        print(f">>> {len(handles)} pico2000 detected")

        self.chandle = None
        for serial, handle in handles.items():
            if serial == self.serial:
                self.chandle = ctypes.c_int16(handle)
                print(
                    f"[INIT] Specified digitizer {self.model} "
                    f"{self.serial} found"
                )
            else:
                ps2000.ps2000_close_unit(handle)
        if self.chandle is None:
            raise DigitizerInitError(
                f"[ERROR] Specified digitizer {self.model} "
                f"{self.serial} not found"
            )

        self.unused_channels = set(["A", "B"]) - set(self.channels)
        self.ch_range  = {}
        self.ch_offset = {"A": 0, "B": 0}
        print(f"[INIT] Setting channels: {self.channels}")
        for ch_idx in self.channels:
            channel_No = ps2000.PS2000_CHANNEL["PS2000_CHANNEL_" + ch_idx]
            self.ch_range[ch_idx] = ps2000.PS2000_VOLTAGE_RANGE[
                "PS2000_" + config.get("voltage_range")[ch_idx]
            ]
            coupling = ps2000.PICO_COUPLING["DC"]
            enabled  = 1
            self.status["setCh" + ch_idx] = ps2000.ps2000_set_channel(
                self.chandle, channel_No, enabled, coupling,
                self.ch_range[ch_idx],
            )
            try:
                assert_pico2000_ok(self.status["setCh" + ch_idx])
            except:
                raise DigitizerInitError(
                    f"[ERROR] Fail to initizlize Channel {ch_idx}"
                )

        for ch_idx in self.unused_channels:
            channel_No = ps2000.PS2000_CHANNEL["PS2000_CHANNEL_" + ch_idx]
            range_     = ps2000.PS2000_VOLTAGE_RANGE["PS2000_2V"]
            coupling   = ps2000.PICO_COUPLING["DC"]
            enabled    = 0
            self.status["setCh" + ch_idx] = ps2000.ps2000_set_channel(
                self.chandle, channel_No, enabled, coupling, range_
            )
            assert_pico2000_ok(self.status["setCh" + ch_idx])

        print(f"[INIT] Setting trigger")
        trigger_channel  = config.get("trigger_channel")
        trig_ch_handle   = ps2000.PS2000_CHANNEL[
            "PS2000_CHANNEL_" + trigger_channel
        ]
        print(f"\tTrigger channel: {trigger_channel}")
        trigger_level_mV = config.get("trigger_level")
        print(f"\tTrigger level {trigger_level_mV} mV")
        self.maxADC = ctypes.c_int16(32767)
        trigger_level_ADC = mV2adc(
            trigger_level_mV, self.ch_range[trigger_channel], self.maxADC
        )
        pre_trigger   = config.get("pre_trigger") * -1
        trigger_type  = 0 if config.get("trigger_edge") == "RISING" else 1
        trigger_str   = "RISING" if trigger_type == 0 else "FALLING"
        print(f"\tTrigger type: {trigger_str}")
        auto_trigger  = config.get("auto_trigger")

        self.status["trigger"] = ps2000.ps2000_set_trigger(
            self.chandle, trig_ch_handle, trigger_level_ADC,
            trigger_type, pre_trigger, auto_trigger,
        )
        try:
            assert_pico2000_ok(self.status["trigger"])
        except:
            raise DigitizerInitError("[ERROR] Fail to set trigger")

        print(f"[INIT] Setting sampling configuration")
        self.sample_number = config.get("sample_number")
        maxsamples         = self.sample_number
        print(f"\tSample number: {self.sample_number}")

        self.timebase       = config.get("timebase")
        timeInterval        = ctypes.c_int32()
        timeUnits           = ctypes.c_int32()
        oversample          = ctypes.c_int16(1)
        maxSamplesReturn    = ctypes.c_int32()
        self.status["getTimebase"] = ps2000.ps2000_get_timebase(
            self.chandle, self.timebase, maxsamples,
            ctypes.byref(timeInterval), ctypes.byref(timeUnits),
            oversample, ctypes.byref(maxSamplesReturn),
        )
        try:
            assert_pico2000_ok(self.status["getTimebase"])
        except:
            raise DigitizerInitError(
                f"[ERROR] Incorrect timebase {self.timebase}"
            )
        print(f"\tSample interval: {timeInterval.value} ns")

        self.cmaxSamples             = ctypes.c_int32(maxsamples)
        self.pico2000_timeIndisposedms = ctypes.c_int32()

        self.bufferMax    = {}
        self.bufferMax["A"] = np.zeros(maxsamples, dtype=np.int16)
        self.bufferMax["B"] = np.zeros(maxsamples, dtype=np.int16)

        self.t       = np.linspace(
            0,
            (self.cmaxSamples.value - 1) * timeInterval.value,
            self.cmaxSamples.value,
        )
        self.delta_t = timeInterval.value
        print("[INIT] Initialization complete")

    def getPico2000Serial(self, handle):
        from picosdk.ps2000 import ps2000
        buf = ctypes.create_string_buffer(64)
        ps2000.ps2000_get_unit_info(
            ctypes.c_int16(handle), buf,
            ctypes.c_int16(len(buf)), ctypes.c_int16(4),
        )
        return buf.value.decode(errors="ignore")

    def pico2000BlockCapture(self):
        from picosdk.ps2000 import ps2000
        from picosdk.functions import assert_pico2000_ok

        oversample = ctypes.c_int16(1)
        self.status["runBlock"] = ps2000.ps2000_run_block(
            self.chandle, self.sample_number, self.timebase,
            oversample, ctypes.byref(self.pico2000_timeIndisposedms),
        )
        assert_pico2000_ok(self.status["runBlock"])

        trig_timeout = 10
        trig_start   = time.time()
        while (ps2000.ps2000_ready(self.chandle) == 0
               and not self.stop_event.is_set()):
            if time.time() - trig_start > trig_timeout:
                print(
                    f"[WARN]: {self.model} {self.serial}: "
                    f"No trigger for {trig_timeout} seconds"
                )
                trig_timeout += 10
            time.sleep(0.01)

        self.status["getValues"] = ps2000.ps2000_get_values(
            self.chandle,
            self.bufferMax["A"].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            self.bufferMax["B"].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            None, None, ctypes.byref(oversample), self.cmaxSamples,
        )
        assert_pico2000_ok(self.status["getValues"])
