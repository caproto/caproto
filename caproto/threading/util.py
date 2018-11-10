import io
import threading
import time
import traceback

debug = True


if debug:
    all_locks = []

    class _Lock:
        def __init__(self, name):
            self.times = []
            self.name = name
            all_locks.append(self)

        def __enter__(self):
            ret = self.lock.__enter__()
            f = io.StringIO()
            traceback.print_stack(file=f)
            stack_string = ''
            self.times.append([f, time.time()])
            return ret

        def __exit__(self, exc_type, exc_value, tb):
            self.times[-1].append(time.time())
            return self.lock.__exit__(exc_type, exc_value, tb)

    def show_wait_times(threshold):
        for lock in all_locks:
            print(lock.name)
            total = 0
            for item in lock.times:
                try:
                    tb, start, stop = item
                except ValueError:
                    continue
                elapsed = stop - start
                if elapsed >= threshold:
                    print(f'+ {elapsed:.3f}')  #   {tb.getvalue()}')
                total += elapsed
            if total > 0.001:
                print(f'  total={total:.3f}')

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

    def show_wait_times(threshold):
        ...
