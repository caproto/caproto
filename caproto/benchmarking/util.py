import os
import subprocess
import shutil
import logging
from contextlib import contextmanager
from tempfile import NamedTemporaryFile


logger = logging.getLogger(__name__)


def find_dbd_path():
    '''Find the path to database definitions, based on the environment'''
    if 'EPICS_BASE' in os.environ:
        return os.path.join(os.environ['EPICS_BASE'], 'dbd')
    else:
        softioc_path = shutil.which('softIoc')
        return os.path.abspath(os.path.join(softioc_path, '..', '..', 'dbd'))


@contextmanager
def softioc(*, db_text='', access_rules_text='', additional_args=None,
            macros=None, dbd_path=None, dbd_name='softIoc.dbd', env=None):
    '''[context manager] Start a soft IOC on-demand

    Parameters
    ----------
    db_text : str
        Database text
    access_rules_text : str
        Access security group text, optional
    additional_args : list
        List of additional args to pass to softIoc
    macros : dict
        Dictionary of key to value
    dbd_path : str, optional
        Path to dbd directory
        Uses `find_dbd_path()` if None
    dbd_name : str
        Name of dbd file
    env : dict
        Environment variables to pass

    Yields
    ------
    proc : subprocess.Process
    '''
    if not access_rules_text:
        access_rules_text = '''
            ASG(DEFAULT) {
                RULE(1,READ)
                RULE(1,WRITE,TRAPWRITE)
            }
            '''

    if additional_args is None:
        additional_args = []

    if macros is None:
        macros = dict(P='test')

    proc_env = dict(os.environ)
    if env is not None:
        proc_env.update(**env)

    logger.debug('soft ioc environment is:')
    for key, val in sorted(proc_env.items()):
        logger.debug('%s = %r', key, val)

    # if 'EPICS_' not in proc_env:

    macros = ','.join('{}={}'.format(k, v) for k, v in macros.items())

    with NamedTemporaryFile(mode='w+') as cf:
        cf.write(access_rules_text)
        cf.flush()

        logger.debug('access rules filename is: %s', cf.name)
        with NamedTemporaryFile(mode='w+') as df:
            df.write(db_text)
            df.flush()

            logger.debug('db filename is: %s', df.name)
            if dbd_path is None:
                dbd_path = find_dbd_path()

            dbd_path = os.path.join(dbd_path, dbd_name)
            logger.debug('dbd path is: %s', dbd_path)
            assert os.path.exists(dbd_path)

            popen_args = ['softIoc',
                          '-D', dbd_path,
                          '-m', macros,
                          '-a', cf.name,
                          '-d', df.name]

            proc = subprocess.Popen(popen_args + additional_args, env=proc_env,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            yield proc

            proc.kill()
            proc.wait()


def make_database(records):
    '''Make an EPICS database from a dictionary of records

    Parameters
    ----------
    records : dict
        Keys: ('record_name', 'record_type')
        Values: dictionary of {'field': 'field_value'}

    Returns
    -------
    Newline-delimited block of text
    '''

    def gen():
        for (record, rtyp), field_info in records.items():
            yield 'record({}, "{}")'.format(rtyp, record)
            yield '{'

            for field_name, field_value in field_info.items():
                yield '    field({}, "{}")'.format(field_name, field_value)
            yield '}'
            yield ''

    return '\n'.join(gen())


class IocHandler:
    '''Benchmarking helper class

    Runs multiple IOCs and handles their cleanup.
    '''

    def __init__(self, logger=None):
        self.logger = (logger if logger is not None
                       else globals()['logger'])
        self._cms = []
        self._softioc_processes = []

    def setup_ioc(self, *, db_text, max_array_bytes=16384, env_vars=None,
                  **kwargs):
        if env_vars is None:
            env_vars = {}

        # NOTE: have to increase EPICS_CA_MAX_ARRAY_BYTES if NELM >= 4096
        #       (remember default is 16384 bytes / sizeof(int32) = 4096)
        env = dict(EPICS_CA_MAX_ARRAY_BYTES=str(max_array_bytes))
        env.update(**env_vars)

        cm = softioc(db_text=db_text, env=env)
        self._cms.append(cm)
        self._softioc_processes.append(cm.__enter__())
        self.logger.debug('Starting IOC with max_array_bytes=%s '
                          'env vars: %r database: %r', max_array_bytes,
                          env_vars, db_text)
        return cm

    def teardown(self):
        for i, cm in enumerate(self._cms[:]):
            self.logger.debug('Tearing down soft IOC context manager #%d', i)
            cm.__exit__(StopIteration, None, None)
            self._cms.remove(cm)

        for i, proc in enumerate(self._softioc_processes[:]):
            self.logger.debug('Killing soft IOC process #%d', i)
            proc.kill()
            self.logger.debug('Waiting for soft IOC process #%d', i)
            proc.wait()
            self._softioc_processes.remove(proc)

        self.logger.debug('IOC teardown complete')

    def wait(self):
        for i, proc in enumerate(self._softioc_processes[:]):
            self.logger.debug('Waiting for soft IOC process #%d', i)
            proc.wait()

        self.logger.debug('Waiting complete')


def set_logging_level(level, *, logger=None):
    'Set logging level of all caproto submodules to the specified level'
    if logger is None:
        logger = globals()['logger']

    for key, logger_ in logging.Logger.manager.loggerDict.items():
        if key.startswith('caproto.'):
            if getattr(logger_, 'level', 0) != level:
                logger_ = logging.getLogger(key)
                logger_.setLevel(level)
                logger.debug('Setting log level of %s to %s', key,
                             logger_.level)
