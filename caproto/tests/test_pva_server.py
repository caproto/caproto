import logging
import os
import signal
import subprocess
import sys
import typing

import pytest

pytest.importorskip('caproto.pva')

from caproto import pva

logger = logging.getLogger(__name__)


def run_example_ioc(module_name: str,
                    *,
                    request,
                    pv_to_check: str,
                    args: typing.Optional[typing.List[str]] = None,
                    stdin=None, stdout=None, stderr=None, very_verbose=True
                    ) -> subprocess.Popen:
    '''
    Run an example IOC by module name as a subprocess.

    Checks a given PV to see if the server is running.

    Parameters
    ----------
    module_name : str
        The fully-qualified module name.

    request :
        The pytest request fixture.

    pv_to_check : str
        The PV to check to see if the server is running.

    args : list, optional
        List of additional arguments to pass to the process.

    Returns
    -------
    subprocess.Popen
        The IOC subprocess.
    '''
    args = args or []

    logger.debug(f'Running {module_name}')

    if '-vvv' not in args and very_verbose:
        args = list(args) + ['-vvv']

    os.environ['COVERAGE_PROCESS_START'] = '.coveragerc'

    process = subprocess.Popen(
        [sys.executable,
         '-um',
         'caproto.tests.example_runner',
         module_name] + list(args),
        stdout=stdout, stderr=stderr, stdin=stdin, env=os.environ,
    )

    def stop_ioc():
        if process.poll() is None:
            if sys.platform != 'win32':
                logger.debug('Sending Ctrl-C to the example IOC')
                process.send_signal(signal.SIGINT)
                logger.debug('Waiting on process...')

            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                logger.debug('IOC did not exit in a timely fashion')
                process.terminate()
                logger.debug('IOC terminated')
            else:
                logger.debug('IOC has exited')
        else:
            logger.debug('Example IOC has already exited')

    if request is not None:
        request.addfinalizer(stop_ioc)

    if pv_to_check:
        poll_readiness(pv_to_check, timeout=5.0, attempts=2, process=process)

    return process


def poll_readiness(pv_to_check: str,
                   attempts: int = 5,
                   timeout: float = 1.0,
                   process: typing.Optional[subprocess.Popen] = None):
    """
    Poll an IOC for readiness by checking a specific PV.

    Parameters
    ----------
    pv_to_check : str

    attempts : int, optional
        The number of retries to perform.

    timeout : float, optional
        The timeout per attempt.

    process : subprocess.Popen, optional
        The subprocess to monitor.

    Raises
    ------
    TimeoutError
        If the attempt fails or the process exits early.
    """
    logger.debug(f'Checking PV {pv_to_check}')
    for _attempt in range(attempts):
        if process is not None and process.returncode is not None:
            raise TimeoutError(f'IOC process exited: {process.returncode}')

        try:
            pva.sync.client.read(pv_to_check, timeout=timeout,
                                 pvrequest='field()')
        except (TimeoutError, ConnectionRefusedError):
            continue
        else:
            return

    raise TimeoutError(
        f"ioc fixture failed to start in {attempts * timeout} "
        f"seconds (pv: {pv_to_check})"
    )


def test_example_ioc_advanced(request, prefix):
    run_example_ioc('caproto.pva.ioc_examples.advanced', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}test')

    initial, res, final = pva.sync.client.read_write_read(
        f'{prefix}test', data={'value': 6, 'info': 'foobar'}
    )
    assert (initial.value, initial.info) == (5, 'a string')
    assert (final.value, final.info) == (6, 'foobar')

    _, value = pva.sync.client.read(f'{prefix}test2')
    assert (value.value, value.info) == (6, 'a different string')

    for _, data in pva.sync.client.monitor(f'{prefix}test2',
                                           pvrequest='field()',
                                           maximum_events=1):
        assert (data.value, data.info) == (6, 'a different string')


def test_example_ioc_group(request, prefix):
    run_example_ioc('caproto.pva.ioc_examples.group', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}test')

    results = [data for _, data in
               pva.sync.client.monitor(f'{prefix}test', pvrequest='field()',
                                       maximum_events=2)
               ]

    assert results[0].value + 1 == results[1].value
    assert f'testing {results[0].value}' == results[0].info
    assert f'testing {results[1].value}' == results[1].info

    # Not sure if you should be able to do this - this _isn't_ an RPC call:
    initial, res, final = pva.sync.client.read_write_read(
        f'{prefix}rpc', data={'value': 6, 'info': 'foobar'}
    )


def test_example_ioc_normative(request, prefix):
    run_example_ioc('caproto.pva.ioc_examples.normative', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}nt_bool')

    def write_and_check(pv, to_write, start_value):
        initial, _, final = pva.sync.client.read_write_read(
            f'{prefix}{pv}', data={'value': to_write},
        )

        if isinstance(start_value, list):
            assert list(initial.value) == start_value
            assert list(final.value) == to_write
        else:
            assert initial.value == start_value
            assert final.value == to_write

    write_and_check('nt_bool', False, True)
    write_and_check('nt_int', 0, 42)
    write_and_check('nt_float', 12.0, 42.1)
    write_and_check('nt_string', 'new value', 'test')

    write_and_check('nt_int_array', [0, 1, 2], [42])
    write_and_check('nt_float_array', [1.0, 2.0, 3.0], [42.1])
    write_and_check('nt_string_array', ['new', 'value'], ['test'])
