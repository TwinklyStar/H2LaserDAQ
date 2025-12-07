import numpy as np
import uproot
import awkward as ak
from datetime import datetime
import time
import threading
import queue
import re

class RootManager:

    _scalar_dtypes = {
        "int8":  np.int8,
        "int16":  np.int16,
        "int32":  np.int32,
        "float32": np.float32,
        "float64": np.float64,
    }

    def __init__(self, filename, runN, sample_num, add_channels=("A","B","C","D"), chunk_size=1000):
        self._runN = runN
        self._file = uproot.recreate(filename)
        self._chConfig = []
        if (sample_num>0):
            self._branch = {
                "Run": "int32", 
                "WaveN": "int32",
                "Year": "int16", 
                "Month": "int8", 
                "Day": "int8", 
                "Hour": "int8", 
                "Min": "int8", 
                "Sec": "int8",
                "ms": "int16", 
                "nTime": "int32",
                "Time": "{} * float32".format(sample_num)}
            for ch in add_channels:
                self._branch[f"Ch{ch}"] = f"{sample_num} * float32"
                self._chConfig.append(f"Ch{ch}")

            self._fixed_length = True
        else:
            self._branch = {
                "Run": "int32", 
                "WaveN": "int32",
                "Year": "int16", 
                "Month": "int8", 
                "Day": "int8", 
                "Hour": "int8", 
                "Min": "int8", 
                "Sec": "int8",
                "ms": "int16", 
                "Time": "var * float32"}
            for ch in add_channels:
                self._branch[f"Ch{ch}"] = "var * float32"
                self._chConfig.append(f"Ch{ch}")

            self._fixed_length = False

        self._tree = self._file.mktree("rawWave", self._branch)
        self._chunk_size = max(1, chunk_size)
        self._sample_num = sample_num

        self._wave_n = 0

        self._buffer_n = 3
        if self._fixed_length:
            self._buffers = [{} for i in range(self._buffer_n)]
            for name, typ in self._branch.items():
                match = re.match(r"^.*\* (.*)", typ)    # Any patter starts with '...* ', and capture rest of parts as data type
                for i in range(self._buffer_n):
                    if match:
                        self._buffers[i][name] = np.empty((self._chunk_size, self._sample_num), dtype=match.group(1))
                    else:
                        self._buffers[i][name] = []
        else:
            self._buffers = [{k: [] for k in self._branch.keys()} for i in range(self._buffer_n)]  # Buffer
        self._buffer_now = 0
        self._n_buffered = [0 for i in range(self._buffer_n)]

        self.max_queued = 2
        self._stop_queue = object()

    def fill(self, **wave):
        now = datetime.now()
        self._buffers[self._buffer_now]["Year"].append(now.year)
        self._buffers[self._buffer_now]["Month"].append(now.month)
        self._buffers[self._buffer_now]["Day"].append(now.day)
        self._buffers[self._buffer_now]["Hour"].append(now.hour)
        self._buffers[self._buffer_now]["Min"].append(now.minute)
        self._buffers[self._buffer_now]["Sec"].append(now.second)
        self._buffers[self._buffer_now]["ms"].append(now.microsecond // 1000)
        self._buffers[self._buffer_now]["Run"].append(self._runN)
        self._buffers[self._buffer_now]["WaveN"].append(self._wave_n)
        
        required_key = self._chConfig[:]
        required_key.append("Time")
        missing = required_key - wave.keys()
        if missing:
            print("ERROR: Missing branch:", missing, "when filling the tree")
            return

        if self._fixed_length:
            self._buffers[self._buffer_now]["nTime"].append(self._sample_num)
            for k, v in wave.items():
                self._buffers[self._buffer_now][k][self._n_buffered[self._buffer_now], :] = v
        else:
            for k, v in wave.items():
                self._buffers[self._buffer_now][k].append(v)
        self._n_buffered[self._buffer_now] += 1
        if self._n_buffered[self._buffer_now] >= self._chunk_size:
            print("Batch full")
            buffer_old = self._buffer_now
            self._q.put(buffer_old)
            self._buffer_now = (self._buffer_now + 1) % self._buffer_n

        self._wave_n += 1

    def start_thread(self):
        self._q = queue.Queue(self.max_queued)
        self._thd = threading.Thread(target=self.background_loop, daemon=True)
        self._thd.start()
        print("Start DAQ thread")
        
    def background_loop(self):
        while True:
            buffer_n = self._q.get()
            if buffer_n is self._stop_queue:
                print("Catch stop signal from queue. Thread stopped.")
                break
            print("Catch buffer ", buffer_n, " from queue")
            self.flush(buffer_n)
            self._q.task_done()

    def flush(self, buffer_n):
        if self._n_buffered[buffer_n] == 0:
            return
        time_start = time.time()
        out = {}
        for name, typ in self._branch.items():
            data = self._buffers[buffer_n][name]

            # Variable-length (jagged) branch: "var * <type>"
            if re.match(r"^.*\*", typ):
                if self._fixed_length:
                    out[name] = data[:self._n_buffered[buffer_n]]
                else:
                    out[name] = ak.Array(data)
            else:
                # Scalar branch: cast to the right dtype
                base = typ.strip()
                if base not in self._scalar_dtypes:
                    raise ValueError(f"Unsupported scalar type '{base}' for branch '{name}'")
                out[name] = np.asarray(data, dtype=self._scalar_dtypes[base])

        print("Conversion takes: ", time.time()-time_start, " secs")
        # Extend once per flush
        self._tree.extend(out)

        # Clear buffers
        if self._fixed_length:
            for name, typ in self._branch.items():
                match = re.match(r"^.*\* (.*)", typ)    # Any patter starts with '...* ', and capture rest of parts as data type
                if match:
                    self._buffers[buffer_n][name] = np.empty((self._chunk_size, self._sample_num), dtype=match.group(1))
                else:
                    self._buffers[buffer_n][name] = []
        else:
            self._buffers[buffer_n] = {k: [] for k in self._branch.keys()}
        self._n_buffered[buffer_n] = 0
        print("Extend takes: ", time.time()-time_start, " secs")

    def close(self):
        self._q.join()                  # Wait for all buffer filled to tree
        self.flush(self._buffer_now)    # Flush remaining data
        self._q.put(self._stop_queue)
        self._file.close()

class StreamManager:
    def SetNoiseRMS(self, RMS):
        self.noise_RMS=RMS

    def SetThreshold(self, thre):
        self.thre = thre
    
    def SetRisingEdge(self):
        self.rising = True

    def SetFallingEdge(self):
        self.rising = False

    def TriggerAndSave(self, signal, rootmng):
        pass

def fastAdc2mV(bufferADC, range, maxADC, offset=0):
    """ 
        adc2mc(
                c_short_Array           bufferADC
                int                     range
                c_int32                 maxADC
                )
               
        Takes a buffer of raw adc count values and converts it into millivolts
    """

    channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]
    vRange = channelInputRanges[range]
    bufferV = bufferADC.astype('int64') * vRange / maxADC.value - offset
    
    return bufferV

def extTrigmV2Adc(voltage_mv):
    return int(voltage_mv / 1000. / 5 * 32767)


class NumpyRingQueue:
    """
    Fixed-capacity ring queue (FIFO) for 1-D numeric data.
    - put(arr): push a 1-D array of values (strict by default)
    - get(n):   pop exactly n values as a contiguous NumPy array
    Works in O(k) copying (k = items moved) and handles wrap-around.
    """
    def __init__(self, max_size: int, dtype='float32'):
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        self.buf = np.empty(max_size, dtype=dtype)
        self.maxsize = max_size
        self.head = 0     # read index
        self.tail = 0     # write index
        self.size = 0     # number of elements currently in queue

    # ----- status -----
    def is_Full(self) -> bool:
        return self.size == self.maxsize

    def is_Null(self) -> bool:
        return self.size == 0

    def capacity(self) -> int:
        return self.maxsize

    def __len__(self) -> int:
        return self.size

    def free_space(self) -> int:
        return self.maxsize - self.size

    # ----- push / pop -----
    def put(self, arr, *, strict: bool = True) -> int:
        """
        Push a 1-D array (or scalar). Returns number of elements written.
        If strict=True, raises if not enough space for all elements.
        """
        a = np.asarray(arr).ravel()
        k = a.size
        if k == 0:
            return 0
        if strict and k > self.free_space():
            raise Exception("Queue full: not enough space to put all elements")
        # write as much as fits (strict=False allows partial)
        k = min(k, self.free_space())

        end = self.maxsize - self.tail
        first = min(k, end)
        # first segment
        self.buf[self.tail:self.tail + first] = a[:first]
        # wrapped segment
        rem = k - first
        if rem:
            self.buf[0:rem] = a[first:first + rem]

        self.tail = (self.tail + k) % self.maxsize
        self.size += k
        return k

    def get(self, n: int):
        """
        Pop exactly n elements as a contiguous NumPy array (copy).
        Raises if not enough data available.
        """
        if n < 0:
            raise ValueError("n must be >= 0")
        if n == 0:
            return np.empty(0, dtype=self.buf.dtype)
        if n > self.size:
            raise Exception("Queue empty: not enough elements to get")

        out = np.empty(n, dtype=self.buf.dtype)
        end = self.maxsize - self.head
        first = min(n, end)
        out[:first] = self.buf[self.head:self.head + first]
        rem = n - first
        if rem:
            out[first:] = self.buf[0:rem]

        self.head = (self.head + n) % self.maxsize
        self.size -= n
        return out

    # ----- convenience (scalar) -----
    def add(self, value):
        # keep your old name; pushes a single value
        return self.put([value], strict=True)

    def delete(self):
        # old name: pop one scalar
        return self.get(1)[0]

    def return_front(self):
        if self.is_Null():
            raise Exception("Queue empty")
        return self.buf[self.head]
        