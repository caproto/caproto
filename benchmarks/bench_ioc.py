import os
from . import util


class IocHandler:
    def __init__(self):
        # NOTE: have to increase EPICS_CA_MAX_ARRAY_BYTES if NELM >= 4096
        #       (remember default is 16384 bytes / sizeof(int32) = 4096)
        self._cms = []
        self._softioc_processes = []

    def setup_ioc(self, *, db_text, max_array_bytes=16384, env_vars=None,
                  **kwargs):
        if env_vars is None:
            env_vars = {}

        env = dict(EPICS_CA_MAX_ARRAY_BYTES=str(max_array_bytes))
        os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = str(max_array_bytes)
        env.update(**env_vars)

        cm = util.softioc(db_text=db_text, env=env)
        self._cms.append(cm)
        self._softioc_processes.append(cm.__enter__())
        return cm

    def teardown(self):
        for cm in self._cms[:]:
            cm.__exit__(StopIteration, None, None)
            self._cms.remove(cm)

        for proc in self._softioc_processes[:]:
            proc.kill()
            proc.wait()
            self._softioc_processes.remove(proc)

    def wait(self):
        for proc in self._softioc_processes:
            proc.wait()


def main():
    db_text = util.make_database(
        {('wfioc:wf4000', 'waveform'): dict(FTVL='LONG', NELM=4000),
         ('wfioc:wf1m', 'waveform'): dict(FTVL='LONG', NELM=1000000),
         ('wfioc:wf2m', 'waveform'): dict(FTVL='LONG', NELM=2000000),
         },
    )

    handler = IocHandler()
    handler.setup_ioc(db_text=db_text, max_array_bytes='10000000')

    try:
        handler.wait()
    except KeyboardInterrupt:
        handler.teardown()


if __name__ == '__main__':
    main()
