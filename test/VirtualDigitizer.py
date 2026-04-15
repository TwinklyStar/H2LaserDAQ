# VirtualDigitizer.py
# Hardware-free subclass of H2LaserDigitizer.
#
# Overrides the three hardware hooks:
#   _init_hardware  — sets up synthetic sampling geometry instead of opening
#                     a PicoScope device
#   _capture_block  — sleeps to enforce 25 Hz, then fills self.bufferMax with
#                     a 500 mV / 1 µs square pulse + white noise
#   _close_hardware — no-op (nothing to disconnect)
#
# run(), close(), and all data-output logic (ROOT, CSV, GUI queue) are
# inherited unchanged from H2LaserDigitizer, so virtual tests exercise
# exactly the same code path as a real acquisition run.

import ctypes
import numpy as np
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.H2LaserDigitizer import H2LaserDigitizer

# Maps voltage-range strings (same as config files) to mV full-scale values.
# Must stay consistent with picoDAQAssistant.fastAdc2mV's lookup table.
_VOLTAGE_RANGES_MV = {
    "10mV": 10, "20mV": 20, "50mV": 50,
    "100mV": 100, "200mV": 200, "500mV": 500,
    "1V": 1000, "2V": 2000, "5V": 5000,
    "10V": 10000, "20V": 20000,
}
_CHANNEL_INPUT_RANGES = [
    10, 20, 50, 100, 200, 500,
    1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000,
]


class VirtualDigitizer(H2LaserDigitizer):
    """
    Drop-in replacement for H2LaserDigitizer that generates synthetic
    waveforms instead of reading from hardware.

    Extra config key required:
        delta_t  (float) : sample interval in ns  (e.g. 10 → 10 ns/sample)
    """

    TRIGGER_RATE_HZ    = 25.0     # simulated acquisition rate
    PULSE_AMPLITUDE_MV = 500.0    # square pulse height  [mV]
    PULSE_WIDTH_NS     = 1000.0   # square pulse width   [ns]

    # -------------------------------------------------------------------------
    # Override 1: replace hardware init with synthetic geometry setup
    # -------------------------------------------------------------------------

    def _init_hardware(self, config):
        self.model  = "virtual"
        self.serial = "VIRTUAL"

        self.sample_number = config.get("sample_number")
        self.delta_t       = config.get("delta_t")   # ns per sample
        self.t = np.linspace(
            0,
            (self.sample_number - 1) * self.delta_t,
            self.sample_number,
            dtype=np.float32,
        )

        # maxADC and ch_range must match the convention used by
        # picoDAQAssistant.fastAdc2mV so the ADC→mV conversion is correct.
        self.maxADC    = ctypes.c_int16(32767)
        self.ch_range  = {}
        self.ch_offset = {}
        for ch in self.channels:
            vrange_str = config.get("voltage_range")[ch]
            vrange_mv  = _VOLTAGE_RANGES_MV[vrange_str]
            self.ch_range[ch]  = _CHANNEL_INPUT_RANGES.index(vrange_mv)
            self.ch_offset[ch] = 0

        self.bufferMax = {
            ch: np.zeros(self.sample_number, dtype=np.int16)
            for ch in self.channels
        }

        # Pre-compute pulse geometry
        self._pre_trigger_sample = int(
            config.get("pre_trigger") / 100.0 * self.sample_number
        )
        self._pulse_samples = max(1, int(self.PULSE_WIDTH_NS / self.delta_t))

        print(
            f"[VIRTUAL INIT] '{self.name}' ready — "
            f"mode={self.run_mode}, "
            f"{self.sample_number} samples @ {self.delta_t} ns/sample, "
            f"window={self.sample_number * self.delta_t / 1000:.1f} µs"
        )

    # -------------------------------------------------------------------------
    # Override 2: generate one synthetic trigger instead of waiting for hardware
    # -------------------------------------------------------------------------

    def _capture_block(self):
        """Sleep to enforce 25 Hz, then fill bufferMax with a square pulse."""
        time.sleep(1.0 / self.TRIGGER_RATE_HZ)

        for ch in self.channels:
            vrange_mv = _CHANNEL_INPUT_RANGES[self.ch_range[ch]]
            adc_amp   = int(
                self.PULSE_AMPLITUDE_MV * self.maxADC.value / vrange_mv
            )
            buf = np.zeros(self.sample_number, dtype=np.int32)
            start = self._pre_trigger_sample
            end   = min(start + self._pulse_samples, self.sample_number)
            buf[start:end] = adc_amp
            # Add ±2 ADC-count white noise (~0.12 mV for 2 V range)
            buf += np.random.randint(-2, 3, size=self.sample_number,
                                     dtype=np.int32)
            self.bufferMax[ch] = np.clip(buf, -32768, 32767).astype(np.int16)

    # -------------------------------------------------------------------------
    # Override 3: nothing to disconnect
    # -------------------------------------------------------------------------

    def _close_hardware(self):
        pass
