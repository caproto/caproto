import os
import pytest
import signal
import subprocess
import time
from caproto._cli import get, put, monitor, parse_data_type
from caproto._dbr import ChannelType

INT_PV = 'pi'
STR_PV = 'str'
ENUM_PV = 'enum'

def escape(pv_name, response):
    raise KeyboardInterrupt

@pytest.mark.parametrize('func,args,kwargs',
                         [(get, ('__does_not_exist',), {}),
                          (put, ('__does_not_exist', 5), {}),
                          (monitor, ('__does_not_exist',),
                           {'callback': escape})])
def test_timeout(func, args, kwargs):
    with pytest.raises(TimeoutError):
        func(*args, **kwargs)


@pytest.mark.parametrize('more_kwargs,',
                         [{'verbose': True},
                          {'repeater': False},
                          {'timeout': 3},
                          ]
                        )
@pytest.mark.parametrize('func,args,kwargs',
                         [(get, (INT_PV,), {}),
                          (put, (INT_PV, 5), {}),
                          (monitor, (INT_PV,), {'callback': escape})
                          ])
def test_options(func, args, kwargs, more_kwargs, ioc):
    kwargs.update(more_kwargs)
    func(*args, **kwargs)


fmt1 = '{response.data[0]}'
fmt2 = '{timestamp:%%H:%%M}'


# Skip the long-running ones.
@pytest.mark.parametrize('command,args',
                         [('caproto-get', ('-h',)),
                          ('caproto-put', ('-h',)),
                          ('caproto-monitor', ('-h',)),
                          ('caproto-get', ('--list-types',)),
                          ('caproto-get', (INT_PV,)),
                          ('caproto-get', (INT_PV, STR_PV)),
                          ('caproto-get', (INT_PV, '-d', '5')),
                          ('caproto-get', (INT_PV, '--format', fmt1)),
                          ('caproto-get', (INT_PV, '--format', fmt2)),
                          ('caproto-get', (ENUM_PV,)),
                          ('caproto-get', (ENUM_PV, '-n')),
                          ('caproto-get', (INT_PV, '-n')),  # no effect
                          ('caproto-get', (INT_PV, '--no-repeater')),
                          ('caproto-get', (INT_PV, '-p', '0')),
                          ('caproto-get', (INT_PV, '-p', '99')),
                          ('caproto-get', (INT_PV, '-t')),
                          ('caproto-get', (INT_PV, '-v')),
                          ('caproto-put', (INT_PV, '5')),
                          ('caproto-put', (INT_PV, '5', '--format', fmt1)),
                          ('caproto-put', (INT_PV, '5', '--format', fmt2)),
                          ('caproto-put', (INT_PV, '5', '--no-repeater')),
                          ('caproto-put', (INT_PV, '5', '-p', '0')),
                          ('caproto-put', (INT_PV, '5', '-p', '99')),
                          ('caproto-put', (INT_PV, '5', '-t')),
                          ('caproto-put', (INT_PV, '5', '-v')),
                          ])
def test_cli(command, args, ioc):
    p = subprocess.Popen([command] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.wait()
    print(p.communicate())
    assert p.poll() == 0


@pytest.mark.parametrize('args',
                         [(INT_PV, '--format', fmt1),
                          (INT_PV, '--format', fmt2),
                          (INT_PV, '--format', '{timedelta}'),
                          (INT_PV, '-m va'),
                          (INT_PV, '-m valp'),
                          (INT_PV, '-m v'),
                          (ENUM_PV,),
                          (ENUM_PV, '-n'),
                          (INT_PV, '-n'),  # should have no effect
                          (INT_PV, '--no-repeater'),
                          (INT_PV, '-p', '0'),
                          (INT_PV, '-p', '99'),
                          (INT_PV, '-w', '2'),
                          ])
def test_monitor(args, ioc):
    p = subprocess.Popen(['caproto-monitor'] + list(args),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Wait for the first line of output.
    line = p.stdout.readline()
    print(line)
    # Process should run forever, therefore should still be running now.
    assert p.poll() is None
    # Send SIGINT. If the CLI is otherwise happy, it should still exit code 0.
    os.kill(p.pid, signal.SIGINT)
    p.wait()
    print(p.communicate())
    assert p.poll() == 0


@pytest.mark.parametrize('data_type', ['enum', 'ENUM', '3'])
def test_parse_data_type(data_type):
    assert parse_data_type(data_type) is ChannelType(3)
