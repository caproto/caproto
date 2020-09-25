import sys
import uuid

import pytest

import caproto.commandline.get
import caproto.commandline.monitor
import caproto.commandline.put
from caproto.sync.client import block, read, subscribe, write

from .conftest import _caproto_ioc, _epics_base_ioc, dump_process_output


@pytest.fixture(scope='module')
def prefix():
    'Random PV prefix for a server'
    return str(uuid.uuid4())[:8] + ':'


@pytest.fixture(params=['caproto', 'epics-base'], scope='module')
def ioc(prefix, request):
    'A fixture that runs more than one IOC: caproto, epics'
    # Get a new prefix for each IOC type:
    if request.param == 'caproto':
        return _caproto_ioc(prefix, request)
    if request.param == 'epics-base':
        return _epics_base_ioc(prefix, request)


def escape(pv_name, response):
    raise KeyboardInterrupt


def fix_arg_prefixes(ioc, args):
    'Add prefix to CLI argument pvnames where necessary'
    return [ioc.pvs.get(arg, arg) for arg in args]


@pytest.mark.parametrize('func,args,kwargs',
                         [(read, ('__does_not_exist',), {}),
                          (write, ('__does_not_exist', 5), {}),
                          ])
def test_timeout(func, args, kwargs):
    with pytest.raises(TimeoutError):
        func(*args, **kwargs)


def test_subscribe_timeout():
    with pytest.raises(TimeoutError):
        sub = subscribe('__does_not_exit')
        sub.block()
    with pytest.raises(TimeoutError):
        sub = subscribe('__does_not_exit')
        block(sub)


def _subprocess_communicate(process, command, timeout=2.0):
    stdout, stderr = process.communicate(timeout=timeout)
    dump_process_output(command, stdout, stderr)
    assert process.poll() == 0


@pytest.mark.parametrize('more_kwargs,',
                         [{'repeater': False},
                          {'timeout': 3},
                          {'notify': True},
                          ]
                         )
@pytest.mark.parametrize('func,args,kwargs',
                         [(read, ('float',), {}),
                          (write, ('float', 3.16), {}),
                          (write, ('float', '3.16'), {'data_type': 0}),
                          ])
def test_options(func, args, kwargs, more_kwargs, ioc):
    args = fix_arg_prefixes(ioc, args)
    kwargs.update(more_kwargs)
    func(*args, **kwargs)


@pytest.mark.parametrize('more_kwargs,',
                         [{'repeater': False},
                          {'timeout': 3},
                          ]
                         )
def test_subscribe_options(more_kwargs, ioc):
    args = ('float',)
    args = fix_arg_prefixes(ioc, args)
    sub = subscribe(*args)
    block(sub, duration=0.5, **more_kwargs)


fmt1 = '{response.data[0]}'
fmt2 = '{timestamp:%%H:%%M}'
fmt3 = '{response.data}'


script_name_to_module = {
    'caproto-get': caproto.commandline.get,
    'caproto-put': caproto.commandline.put,
    'caproto-monitor': caproto.commandline.monitor,
}


def call_script(monkeypatch, script, args):
    module = script_name_to_module[script]
    script_main = module.main

    def no_op(*args, **kwargs):
        ...

    monkeypatch.setattr(module, '_set_handler_with_logger', no_op)
    monkeypatch.setattr(module, 'set_handler', no_op)
    monkeypatch.setattr(sys, 'argv', [script, *args])
    return script_main()


# Skip the long-running ones.
@pytest.mark.timeout(10)
@pytest.mark.parametrize('command,args',
                         [('caproto-get', ('-h',)),
                          ('caproto-put', ('-h',)),
                          ('caproto-monitor', ('-h',)),
                          ('caproto-get', ('--list-types',)),
                          ('caproto-get', ('float',)),
                          ('caproto-get', ('float', 'str')),
                          # data_type as int, enum name, class on type
                          ('caproto-get', ('float', '-d', '0')),
                          ('caproto-get', ('float', '-d', 'STRING')),
                          ('caproto-get', ('float', '-d', 'string')),
                          ('caproto-get', ('float', '-d', 'DBR_STRING')),
                          ('caproto-get', ('float', '-d', 'dbr_string')),
                          ('caproto-get', ('float', '-d', 'CONTROL')),
                          ('caproto-get', ('float', '-d', 'control')),
                          ('caproto-get', ('float', '-d', 'DBR_CONTROL')),
                          ('caproto-get', ('float', '-d', 'dbr_control')),
                          ('caproto-get', ('float', '--format', fmt1)),
                          ('caproto-get', ('float', '--format', fmt2)),
                          ('caproto-get', ('float', '--format', fmt3)),
                          ('caproto-put', ('enum', '0')),
                          ('caproto-put', ('enum', '1')),
                          ('caproto-put', ('enum', 'a')),
                          ('caproto-put', ('enum', 'b')),
                          ('caproto-get', ('enum',)),
                          ('caproto-get', ('enum', '-n')),
                          ('caproto-get', ('float', '-n')),  # no effect
                          ('caproto-get', ('float', '--no-repeater')),
                          ('caproto-get', ('float', '-p', '0')),
                          ('caproto-get', ('float', '-p', '99')),
                          ('caproto-get', ('float', '-t')),
                          ('caproto-get', ('float', '-l')),
                          ('caproto-get', ('float', '-v')),
                          ('caproto-get', ('float', '-vvv')),
                          ('caproto-put', ('float', '3.16')),
                          ('caproto-put', ('float', '3.16', '--format', fmt1)),
                          ('caproto-put', ('float', '3.16', '--format', fmt2)),
                          ('caproto-put', ('float', '3.16', '--no-repeater')),
                          ('caproto-put', ('float', '3.16', '-p', '0')),
                          ('caproto-put', ('float', '3.16', '-p', '99')),
                          ('caproto-put', ('float', '3.16', '-t')),
                          ('caproto-put', ('float', '3.16', '-l')),
                          ('caproto-put', ('float', '3.16', '-v')),
                          ('caproto-put', ('float', '3.16', '-vvv')),
                          # Tests for output formatting arguments:
                          #    floating point -e -f -g -s -lx -lo -lb
                          ('caproto-get', ('float', '-e5')),
                          ('caproto-get', ('float', '-e', '5')),
                          ('caproto-get', ('float', '-f5')),
                          ('caproto-get', ('float', '-f', '5')),
                          ('caproto-get', ('float', '-g5')),
                          ('caproto-get', ('float', '-g', '5')),
                          ('caproto-get', ('float', '-s')),
                          ('caproto-get', ('float', '-lx')),
                          ('caproto-get', ('float', '-lo')),
                          ('caproto-get', ('float', '-lb')),
                          # All at once (the last one is used for output formatting)
                          ('caproto-get', ('float', '-e5', '-f5', '-g5', '-s', '-lx', '-lo', '-lb')),
                          #    integer -0x -0o -0b
                          ('caproto-get', ('int', '-0x')),
                          ('caproto-get', ('int', '-0o')),
                          ('caproto-get', ('int', '-0b')),
                          # All at once (the last one is used for output formatting)
                          ('caproto-get', ('int', '-0x', '-0o', '-0b')),
                          # Test separator (single character)
                          ('caproto-get', ('float', '-F-')),
                          ('caproto-get', ('float', "-F'-'")),
                          ('caproto-get', ('float', '-F', '-')),
                          ('caproto-get', ('float', '-F', "'='")),
                          ('caproto-get', ('waveform', '-F', "'-'")),
                          # Test separator (multiple characters, not supported by EPICS caget)
                          ('caproto-get', ('float', '--wide', '-F', "' = '")),
                          # Test data_count limiter.
                          ('caproto-get', ('waveform', '-#', '1')),
                          ])
def test_cli(command, args, ioc, monkeypatch):
    args = fix_arg_prefixes(ioc, args)
    try:
        call_script(monkeypatch, command, args)
    except SystemExit as ex:
        assert ex.code == 0


@pytest.mark.timeout(5)
@pytest.mark.parametrize('args',
                         [('float', '--format', fmt1),
                          ('float', '--format', fmt2),
                          ('float', '--format', '{timedelta}'),
                          ('float', '-m va'),
                          ('float', '-m valp'),
                          ('float', '-m v'),
                          ('enum',),
                          ('enum', '-n'),
                          ('float', '-n'),  # should have no effect
                          ('float', '--no-repeater'),
                          ('float', '-p', '0'),
                          ('float', '-p', '99'),
                          ('float', '-w', '2'),
                          # Tests for output formatting arguments:
                          #    floating point -e -f -g -s -lx -lo -lb
                          ('float', '-e5'),
                          ('float', '-e', '5'),
                          ('float', '-f5'),
                          ('float', '-f', '5'),
                          ('float', '-g5'),
                          ('float', '-g', '5'),
                          ('float', '-s'),
                          ('float', '-lx'),
                          ('float', '-lo'),
                          ('float', '-lb'),
                          # All at once (the last one is used for output formatting)
                          ('float', '-e5', '-f5', '-g5', '-s', '-lx', '-lo', '-lb'),
                          #    integer -0x -0o -0b
                          ('int', '-0x'),
                          ('int', '-0o'),
                          ('int', '-0b'),
                          # All at once (the last one is used for output formatting)
                          ('int', '-0x', '-0o', '-0b'),
                          # Test separator (single character)
                          ('float', '-F-'),
                          ('float', "-F'-'"),
                          ('float', '-F', '-'),
                          ('float', '-F', "'='"),
                          ('waveform', '-F', "'-'"),
                          # Test separator (multiple characters, not supported by EPICS monitor)
                          ('float', '-F', "' = '"),
                          # Test data_count limiter.
                          ('waveform', '-#', '1'),
                          ])
def test_monitor(args, ioc, monkeypatch):
    args = fix_arg_prefixes(ioc, args)

    # For the purposes of this test, one monitor output is sufficient
    args += ['--maximum', '1']
    call_script(monkeypatch, 'caproto-monitor', args)
