import io
import threading
import time
import traceback

debug = False


if debug:
    all_locks = []
    all_events = []

    class _Lock:
        def __init__(self, name):
            self.hold_times = []
            self.acquire_times = []
            self.name = name
            all_locks.append(self)

        def __enter__(self):
            f = io.StringIO()
            traceback.print_stack(file=f)
            pre_acquire = time.time()
            self.lock.acquire()
            acquired = time.time()
            self.acquire_times.append([f, pre_acquire, acquired])
            self.hold_times.append([f, acquired])

        def __exit__(self, exc_type, exc_value, tb):
            self.hold_times[-1].append(time.time())
            self.lock.release()

    class RLock(_Lock):
        def __init__(self, name):
            super().__init__(name)
            self.lock = threading.RLock()

    class Lock(_Lock):
        def __init__(self, name):
            self.lock = threading.Lock()

    class Event(threading.Event):
        def __init__(self, name):
            super().__init__()
            self.name = name
            self.wait_times = []
            all_events.append(self)

        def wait(self, timeout=None):
            # f = io.StringIO()
            # traceback.print_stack(file=f)
            start = time.time()
            ret = super().wait(timeout=timeout)
            stop = time.time()
            self.wait_times.append([None, start, stop])
            return ret

    class Telemetry:
        def __init__(self, name):
            super().__init__()
            self.name = name
            self.wait_times = []
            all_events.append(self)
            self.t0 = None
            self.t1 = None

        def record_time(self, t0, t1):
            # f = io.StringIO()
            # traceback.print_stack(file=f)
            self.wait_times.append([None, t0, t1])

        def __enter__(self):
            self.t0 = time.time()

        def __exit__(self, exc_type, exc_value, tb):
            self.t1 = time.time()
            self.wait_times.append(['', self.t0, self.t1])

    def show_wait_times(threshold, *, show_stack=False):
        for obj in all_locks + all_events:
            if isinstance(obj, _Lock):
                types = [('hold', obj.hold_times),
                         ('acquire', obj.acquire_times)]
            else:
                types = [('wait', obj.wait_times),
                         ]

            for time_type, list_ in types:
                total = 0
                for item in list_:
                    try:
                        stack, start, stop = item
                    except ValueError:
                        continue
                    elapsed = stop - start
                    if elapsed >= threshold:
                        print(f'+ {obj.name} {time_type} {elapsed:.3f}')
                        if show_stack and stack is not None:
                            print(f'Stack: {stack.getvalue()}')
                    total += elapsed
                if total > 0.001 and len(list_) > 1:
                    print(f'-> {obj.name} {time_type} total={total:.3f} '
                          f'count={len(list_)}')

else:
    def RLock(name):
        return threading.RLock()

    def Lock(name):
        return threading.Lock()

    def Event(name):
        return threading.Event()

    class Telemetry:
        def __init__(self, name):
            super().__init__()

        def record_time(self, t0, t1):
            self.wait_times.append([None, t0, t1])

        def __enter__(self):
            ...

        def __exit__(self, exc_type, exc_value, tb):
            ...

    def show_wait_times(threshold):
        ...
