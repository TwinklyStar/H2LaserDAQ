# h2_manager.py
import queue
import threading

from H2LaserDigitizer import H2LaserDigitizer

class H2LaserDAQManager:
    def __init__(self, digitizer_configs):
        """
        digitizer_configs: dict from name -> config dict
        (e.g. h2_config.DIGITIZER_CONFIGS)
        """
        self.update_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.workers = []

        for name, cfg in digitizer_configs.items():
            worker = H2LaserDigitizer(
                name=name,
                config=cfg,
                update_queue=self.update_queue,
                stop_event=self.stop_event,
            )
            self.workers.append(worker)

    def start_all(self):
        for w in self.workers:
            w.start()

    def stop_all(self):
        self.stop_event.set()
        for w in self.workers:
            w.join()
            w.close()