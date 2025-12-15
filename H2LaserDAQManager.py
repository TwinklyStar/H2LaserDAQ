# h2_manager.py
import queue
import threading
from H2Exceptions import DigitizerInitError
from utility import log
from H2LaserDigitizer import H2LaserDigitizer

class H2LaserDAQManager:
    def __init__(self, digitizer_configs):
        """
        digitizer_configs: dict from name -> config dict
        (e.g. h2_config.DIGITIZER_CONFIGS)
        """
        self.update_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.workers = {}

        print("[INIT] Loading digitizer configuration...")
        try:
            for name, cfg in digitizer_configs.items():
                worker = H2LaserDigitizer(
                    name=name,
                    config=cfg,
                    update_queue=self.update_queue,
                    stop_event=self.stop_event,
                )
                self.workers[name]=worker
        except DigitizerInitError as e:
            log(e)
            log("[FATAL] DAQ initialization failed. Exiting.")
            self.stop_all()
            raise SystemExit(1)

    def start_all(self):
        for w in self.workers.values():
            w.start()

    def stop_all(self):
        self.stop_event.set()
        print("[EXIT] Stopping DAQ threads...")
        for w in self.workers.values():
            print(f"[EXIT] Stopping digitizer {w.model} {w.serial}")
            w.join()
            w.close()
        print("[EXIT] All digitizer stopped")