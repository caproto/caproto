import pytest
import subprocess
from caproto._cli import get, put, monitor, parse_data_type
from caproto._dbr import ChannelType


PV1 = 'Py:ao1'
PV2 = 'Py:ao1.DESC'


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
                         [(get, (PV1,), {}),
                          (put, (PV1, 5), {}),
                          (monitor, (PV1,), {'callback': escape})
                          ])
def test_options(func, args, kwargs, more_kwargs):
    kwargs.update(more_kwargs)
    func(*args, **kwargs)


fmt1 = '{repsonse.data[0]}'
fmt2 = '{timestamp:%H:%M}'


# Skip the long-running ones.
@pytest.mark.parametrize('command,args',
                         [('caproto-get', ('-h',)),
                          ('caproto-put', ('-h',)),
                          ('caproto-monitor', ('-h',)),
                          ('caproto-get', ('--list-types',)),
                          ('caproto-get', (PV1,)),
                          ('caproto-get', (PV1, PV2)),
                          ('caproto-get', (PV1, '-d', '5')),
                          ('caproto-get', (PV1, '--format', fmt1)),
                          ('caproto-get', (PV1, '--format', fmt2)),
                          ('caproto-get', (PV1, '-n')),
                          ('caproto-get', (PV1, '--no-repeater')),
                          ('caproto-get', (PV1, '-p', '0')),
                          ('caproto-get', (PV1, '-p', '99')),
                          ('caproto-get', (PV1, '-t')),
                          ('caproto-get', (PV1, '-v')),
                          ('caproto-put', (PV1, '5')),
                          ('caproto-put', (PV1, '5', '--format', fmt1)),
                          ('caproto-put', (PV1, '5', '--format', fmt2)),
                          ('caproto-put', (PV1, '5', '--no-repeater')),
                          ('caproto-put', (PV1, '5', '-p', '0')),
                          ('caproto-put', (PV1, '5', '-p', '99')),
                          ('caproto-put', (PV1, '5', '-t')),
                          ('caproto-put', (PV1, '5', '-v')),
                          ])
def test_cli(command, args):
    p = subprocess.Popen([command] + list(args))
    p.wait()
    assert p.returncode == 0


@pytest.mark.parametrize('data_type', ['enum', 'ENUM', '3'])
def test_parse_data_type(data_type):
    assert parse_data_type(data_type) is ChannelType(3)
