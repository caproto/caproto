import pytest
import subprocess
from caproto.cli import get, put, monitor


PV_NAME = 'Py:ao1'


def escape(response):
    raise KeyboardInterrupt

@pytest.mark.parametrize('func,args',
                         [(get, ('__does_not_exist',)),
                          (put, ('__does_not_exist', 5)),
                          (monitor, ('__does_not_exist', escape))])
def test_timeout(func, args):
    with pytest.raises(TimeoutError):
        func(*args)


@pytest.mark.parametrize('kwargs,',
                         [{'verbose': True},
                          {'repeater': False},
                          {'timeout': 3},
                          ]
                        )
@pytest.mark.parametrize('func,args',
                         [(get, (PV_NAME,)),
                          (put, (PV_NAME, 5)),
                          (monitor, (PV_NAME, escape))
                          ])
def test_options(func, args, kwargs):
    func(*args, **kwargs)


# Skip the long-running ones.
@pytest.mark.parametrize('command,args',
                         [('caproto-get', (PV_NAME,)),
                          ('caproto-put', (PV_NAME, '5')),
                          ])
def test_cli(command, args):
    p = subprocess.Popen([command] + list(args))
    p.wait()
    assert p.returncode == 0
