import pytest
import subprocess
from caproto._cli import get, put, monitor


# PV_NAME = 'Py:ao1'
PV_NAME = 'pi'


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
                         [(get, (PV_NAME,), {}),
                          (put, (PV_NAME, 5), {}),
                          (monitor, (PV_NAME,), {'callback': escape})
                          ])
def test_options(func, args, kwargs, more_kwargs):
    kwargs.update(more_kwargs)
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
