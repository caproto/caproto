import sys

import pytest

pytest.importorskip('caproto.pva')

import caproto.pva.commandline


@pytest.mark.parametrize(
    'func',
    [pytest.param(caproto.pva.commandline.get.main, id='get'),
     pytest.param(caproto.pva.commandline.put.main, id='put'),
     pytest.param(caproto.pva.commandline.monitor.main, id='monitor')]
)
def test_help_and_version(func, monkeypatch):
    monkeypatch.setattr(sys, 'argv', [sys.argv[0], '--help'])
    with pytest.raises(SystemExit):
        func()

    monkeypatch.setattr(sys, 'argv', [sys.argv[0], '--version'])
    with pytest.raises(SystemExit):
        func()
