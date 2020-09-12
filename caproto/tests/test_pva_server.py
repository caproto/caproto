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


def test_basic(request, prefix):
    run_example_ioc('caproto.pva.ioc_examples.basic', request=request,
                    args=['--prefix', prefix], pv_to_check=f'{prefix}test')

    value = pva.sync.client.read(f'{prefix}test')
    inst = value.dataclass_instance
    assert (inst.value, inst.info) == (5, 'a string')

    value = pva.sync.client.read(f'{prefix}test2')
    inst = value.dataclass_instance
    assert (inst.value, inst.info) == (6, 'a different string')
