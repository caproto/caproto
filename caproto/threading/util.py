import time
import threading

debug = True


if debug:
    all_locks = []

    class _Lock:
        def __init__(self, name):
            self.times = []
            self.name = name
            all_locks.append(self)

        def __enter__(self):
            self.times.append([time.time()])
            return self.lock.__enter__()

        def __exit__(self, exc_type, exc_value, traceback):
            self.times[-1].append(time.time())
            return self.lock.__exit__(exc_type, exc_value, traceback)

    def show_wait_times(threshold):
        for lock in all_locks:
            print(lock.name)
            for item in lock.times:
                try:
                    start, stop = item
                except ValueError:
                    continue
                elapsed = stop - start
                if elapsed >= threshold:
                    print(f'+ {elapsed:.3f}')

    class RLock(_Lock):
        def __init__(self, name):
            super().__init__(name)
            self.lock = threading.RLock()

    class Lock(_Lock):
        def __init__(self, name):
            self.lock = threading.Lock()
else:
    def RLock(name):
        return threading.RLock()

    def Lock(name):
        return threading.Lock()
