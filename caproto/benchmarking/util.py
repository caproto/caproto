import os
import sys
import subprocess
import shutil
import logging
from contextlib import contextmanager

from .._utils import named_temporary_file


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

    proc_env = os.environ.copy()
    if env is not None:
        proc_env.update(**env)

    logger.debug('soft ioc environment is:')
    for key, val in sorted(proc_env.items()):
        if not key.startswith('_'):
            logger.debug('%s = %r', key, val)

    # if 'EPICS_' not in proc_env:

    macros = ','.join('{}={}'.format(k, v) for k, v in macros.items())

    with named_temporary_file(mode='w+') as cf:
        cf.write(access_rules_text)
        cf.flush()
        cf.close()  # win32_compat

        logger.debug('access rules filename is: %s', cf.name)
        with named_temporary_file(mode='w+') as df:
            df.write(db_text)
            df.flush()
            df.close()  # win32_compat

            logger.debug('db filename is: %s', df.name)
            if dbd_path is None:
                dbd_path = find_dbd_path()

            dbd_path = os.path.join(dbd_path, dbd_name)
            logger.debug('dbd path is: %s', dbd_path)

            popen_args = ['softIoc',
                          '-D', dbd_path,
                          '-m', macros,
                          '-a', cf.name,
                          '-d', df.name]

            if sys.platform == 'win32':
                si = subprocess.STARTUPINFO()
                si.dwFlags = (subprocess.STARTF_USESTDHANDLES |
                              subprocess.CREATE_NEW_PROCESS_GROUP)
                os_kwargs = dict(startupinfo=si)
            else:
                os_kwargs = {}

            proc = subprocess.Popen(popen_args + additional_args, env=proc_env,
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    **os_kwargs)
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

        cm = softioc(db_text=db_text, env=env, **kwargs)
        self._cms.append(cm)
        self._softioc_processes.append(cm.__enter__())
        self.logger.debug('Starting IOC with max_array_bytes=%s '
                          'env vars: %r database: %r', max_array_bytes,
                          env_vars, db_text)
        return cm

    @property
    def processes(self):
        return list(self._softioc_processes)

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


# vendored from https://github.com/pyepics/testioc/tree/master/testiocApp/Db
# to test that caproto's pyepics shim passes (selections from) the pyepics test
# suite
PYEPICS_TEST_DB = """
record(mbbo,"$(P)mbbo1") {
    field(DESC,"mbbo")
        field(ZRVL,"0")
        field(ZRST,"Stop")
        field(ONVL,"1")
        field(ONST,"Start")
        field(TWVL,"2")
        field(TWST,"Pause")
        field(THVL,"3")
        field(THST,"Resume")
}
record(mbbo,"$(P)mbbo2") {
    field(DESC,"mbbo")
        field(ZRVL,"0")
        field(ZRST,"Stop")
        field(ONVL,"1")
        field(ONST,"Start")
        field(TWVL,"2")
        field(TWST,"Pause")
        field(THVL,"3")
        field(THST,"Resume")
}

record(mbbo,"$(P)pause") {
    field(DESC,"mbbo")
        field(ZRVL,"0")
        field(ZRST,"Not Paused")
        field(ONVL,"1")
        field(ONST,"Paused")
}

record(waveform,"$(P)char128")  {
       field(DTYP,"Soft Channel")
       field(DESC,"short char waveform")
       field(NELM,"128")
       field(FTVL,"UCHAR")
}

record(waveform,"$(P)char256")  {
       field(DTYP,"Soft Channel")
       field(DESC,"short char waveform")
       field(NELM,"256")
       field(FTVL,"UCHAR")
}

record(waveform,"$(P)char2k")  {
       field(DTYP,"Soft Channel")
       field(DESC,"medium char waveform")
       field(NELM,"2048")
       field(FTVL,"UCHAR")
}

record(waveform,"$(P)char64k")  {
       field(DESC,"long char waveform")
       field(DTYP,"Soft Channel")
       field(NELM,"65536")
       field(FTVL,"UCHAR")
}

record(waveform,"$(P)double128")  {
       field(DTYP,"Soft Channel")
       field(DESC,"short double waveform")
       field(NELM,"128")
       field(FTVL,"DOUBLE")
}

record(waveform,"$(P)double2k")  {
       field(DTYP,"Soft Channel")
       field(DESC,"medium double waveform")
       field(NELM,"2048")
       field(FTVL,"DOUBLE")
}

record(waveform,"$(P)double64k")  {
       field(DESC,"long double waveform")
       field(DTYP,"Soft Channel")
       field(NELM,"65536")
       field(FTVL,"DOUBLE")
}

record(waveform,"$(P)long128")  {
       field(DTYP,"Soft Channel")
       field(DESC,"short long waveform")
       field(NELM,"128")
       field(FTVL,"LONG")
}

record(waveform,"$(P)long2k")  {
       field(DTYP,"Soft Channel")
       field(DESC,"medium long waveform")
       field(NELM,"2048")
       field(FTVL,"LONG")
}

record(waveform,"$(P)long64k")  {
       field(DESC,"long long waveform")
       field(DTYP,"Soft Channel")
       field(NELM,"65536")
       field(FTVL,"LONG")
}

record(waveform,"$(P)string128")  {
       field(DTYP,"Soft Channel")
       field(DESC,"short string waveform")
       field(NELM,"128")
       field(FTVL,"STRING")
}

record(waveform,"$(P)string2k")  {
       field(DTYP,"Soft Channel")
       field(DESC,"medium string waveform")
       field(NELM,"2048")
       field(FTVL,"STRING")
}

record(waveform,"$(P)string64k")  {
       field(DESC,"long string waveform")
       field(DTYP,"Soft Channel")
       field(NELM,"65536")
       field(FTVL,"STRING")
}

record(longin,"$(P)long1") {
        field(DESC,"longin")
    field(DESC, "Soft Channel")
    field(VAL,  "123456")
}

record(longout,"$(P)long2") {
        field(DESC,"longout")
    field(DTYP, "Soft Channel")
    field(VAL,  "543210")
}

record(longout,"$(P)long3") {
        field(DESC,"longout")
    field(DTYP, "Soft Channel")
    field(VAL,  "543210")
}

record(longout,"$(P)long4") {
        field(DESC,"longout")
    field(DTYP, "Soft Channel")
    field(VAL,  "543210")
}


record(stringin,"$(P)str1") {
        field(DESC,"stringin")
    field(DTYP, "Soft Channel")
    field(VAL,  "s")
}

record(stringout,"$(P)str2") {
        field(DESC,"stringout")
    field(DTYP, "Soft Channel")
    field(VAL,  "")
}

record(ao,"$(P)ao1") {
    field(DESC, "ao")
    field(VAL,  "1")
}

record(ai,"$(P)ai1") {
    field(DESC, "ai")
    field(VAL,  "1")
}

record(ao,"$(P)ao2") {
    field(DESC, "ao")
    field(VAL,  "1")
}

record(ao,"$(P)ao3") {
    field(DESC, "ao")
    field(VAL,  "1")
}

record(ao,"$(P)ao4") {
    field(DESC, "ao")
    field(VAL,  "1")
}

record(bo,"$(P)bo1") {
    field(DESC, "bo")
    field(VAL,  "1")
}

record(bi,"$(P)bi1") {
    field(DESC, "bi")
    field(VAL,  "1")
}

record(subArray, "$(P)subArr1") {
  field(DESC, "sub array 1")
  field(NELM, "16")
  field(INP, "$(P)wave_test.VAL")
  field(INDX, "0")
  field(FTVL, "DOUBLE")
  field(MALM, "64")
}

record(subArray, "$(P)subArr2") {
  field(DESC, "sub array 2")
  field(NELM, "16")
  field(INP, "$(P)wave_test.VAL")
  field(INDX, "16")
  field(FTVL, "DOUBLE")
  field(MALM, "64")
}

record(subArray, "$(P)subArr3") {
  field(DESC, "sub array 3")
  field(NELM, "16")
  field(INP, "$(P)wave_test.VAL")
  field(INDX, "32")
  field(FTVL, "DOUBLE")
  field(MALM, "64")
}

record(subArray, "$(P)subArr4") {
  field(DESC, "sub array 4")
  field(NELM, "16")
  field(INP, "$(P)wave_test.VAL")
  field(INDX, "48")
  field(FTVL, "DOUBLE")
  field(MALM, "64")
}

record(subArray, "$(P)ZeroLenSubArr1") {
  field(DESC, "zero-length subarray")
  field(NELM, "1")
  field(INDX, "0")
  field(FTVL, "DOUBLE")
  field(MALM, "64")
}

record(fanout, "$(P)mylinker") {
  field(FLNK, "$(P)subArr1")
  field(LNK1, "$(P)subArr3")
  field(LNK2, "$(P)subArr2")
  field(LNK3, "$(P)subArr4")
}

record(waveform, "$(P)wave_test") {
  field(NELM, "64")
  field(FTVL, "DOUBLE")
  field(EGU, "Counts")
  field(SCAN, "Passive")
  field(FLNK, "$(P)mylinker")
}


record(bi,"$(P)xbi") {
  field(DESC, "bi")
  field(VAL,  "1")
  field(FLNK, "$(P)xbo")
}


record(bi,"$(P)xbo") {
  field(DESC, "bo")
  field(VAL,  "0")
}
"""
