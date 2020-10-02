import ast
import asyncio
import copy
import datetime
import sys
import time

import pytest

import caproto as ca

from caproto import ChannelType
from .epics_test_utils import (run_caget, run_caput, has_caget, has_caput)
from .conftest import array_types, run_example_ioc
from caproto.sync.client import write, read, ErrorResponseReceived


caget_checks = sum(
    ([(pv, dtype),
      (pv, ca.field_types['status'][dtype]),
      (pv, ca.field_types['time'][dtype]),
      (pv, ca.field_types['control'][dtype]),
      (pv, ca.field_types['graphic'][dtype]),
      ]
     for pv in ('int', 'pi', 'enum')
     for dtype in ca.native_types),
    []
)

caget_checks += [('char', ChannelType.CHAR),
                 ('char', ChannelType.STS_CHAR),
                 ('char', ChannelType.TIME_CHAR),
                 ('char', ChannelType.GR_CHAR),
                 ('char', ChannelType.CTRL_CHAR),
                 ('str', ChannelType.STRING),
                 ('str', ChannelType.STS_STRING),
                 ('str', ChannelType.TIME_STRING),

                 ('str', ChannelType.STSACK_STRING),
                 ('str', ChannelType.CLASS_NAME),
                 ]


@pytest.mark.skipif(not has_caget(), reason='No caget binary')
@pytest.mark.parametrize('pv, dbr_type', caget_checks)
def test_with_caget(backends, prefix, pvdb_from_server_example, server, pv,
                    dbr_type):
    caget_pvdb = {prefix + pv_: value
                  for pv_, value in pvdb_from_server_example.items()}
    pv = prefix + pv
    ctrl_keys = ('upper_disp_limit', 'lower_alarm_limit',
                 'upper_alarm_limit', 'lower_warning_limit',
                 'upper_warning_limit', 'lower_ctrl_limit',
                 'upper_ctrl_limit', 'precision')

    test_completed = False

    async def client(*client_args):
        nonlocal test_completed

        # args are ignored for curio and trio servers.
        print('* client caget test: pv={} dbr_type={}'.format(pv, dbr_type))
        print(f'(client args: {client_args})')

        db_entry = caget_pvdb[pv]
        # native type as in the ChannelData database
        db_native = ca.native_type(db_entry.data_type)
        # native type of the request
        req_native = ca.native_type(dbr_type)

        data = await run_caget(server.backend, pv, dbr_type=dbr_type)
        print('dbr_type', dbr_type, 'data:')
        print(data)

        db_value = db_entry.value

        # convert from string value to enum if requesting int
        if (db_native == ChannelType.ENUM and
                not (req_native == ChannelType.STRING or
                     dbr_type in (ChannelType.CTRL_ENUM,
                                  ChannelType.GR_ENUM))):
            db_value = db_entry.enum_strings.index(db_value)
        if req_native in (ChannelType.INT, ChannelType.LONG, ChannelType.CHAR):
            if db_native == ChannelType.CHAR:
                assert int(data['value']) == ord(db_value)
            else:
                assert int(data['value']) == int(db_value)
        elif req_native in (ChannelType.STSACK_STRING, ):
            db_string_value = db_entry.alarm.alarm_string
            string_length = len(db_string_value)
            read_value = data['value'][:string_length]
            assert read_value == db_string_value
        elif req_native in (ChannelType.CLASS_NAME, ):
            assert data['class_name'] == 'caproto'
        elif req_native in (ChannelType.FLOAT, ChannelType.DOUBLE):
            assert float(data['value']) == float(db_value)
        elif req_native == ChannelType.STRING:
            if db_native == ChannelType.STRING:
                db_string_value = str(db_value[0])
                string_length = len(db_string_value)
                read_value = data['value'][:string_length]
                assert int(data['element_count']) == 1
                assert read_value == db_string_value
                # due to how we monitor the caget output, we get @@@s where
                # null padding bytes are. so long as we verify element_count
                # above and the set of chars that should match, this assertion
                # should pass
            else:
                assert data['value'] == str(db_value)
        elif req_native == ChannelType.ENUM:
            bad_strings = ['Illegal Value (', 'Enum Index Overflow (']
            for bad_string in bad_strings:
                if data['value'].startswith(bad_string):
                    data['value'] = data['value'][len(bad_string):-1]

            if (db_native == ChannelType.ENUM and
                    (dbr_type in (ChannelType.CTRL_ENUM,
                                  ChannelType.GR_ENUM))):
                # ctrl enum gets back the full string value
                assert data['value'] == db_value
            else:
                assert int(data['value']) == int(db_value)
        else:
            raise ValueError('TODO ' + str(dbr_type))

        # TODO metadata should be cast to requested type as well!
        same_type = (ca.native_type(dbr_type) == db_native)

        if (dbr_type in ca.control_types and same_type and
                dbr_type != ChannelType.CTRL_ENUM):
            for key in ctrl_keys:
                if (key == 'precision' and
                        ca.native_type(dbr_type) != ChannelType.DOUBLE):
                    print('skipping', key)
                    continue
                print('checking', key)
                assert float(data[key]) == getattr(db_entry, key), key

        if dbr_type in ca.time_types:
            timestamp = datetime.datetime.fromtimestamp(db_entry.timestamp)
            assert data['timestamp'] == timestamp

        if (dbr_type in ca.time_types or dbr_type in ca.status_types or
                dbr_type == ChannelType.STSACK_STRING):
            severity = data['severity']
            if not severity.endswith('_ALARM'):
                severity = '{}_ALARM'.format(severity)
            severity = getattr(ca._dbr.AlarmSeverity, severity)
            assert severity == db_entry.severity, key

            status = data['status']
            status = getattr(ca._dbr.AlarmStatus, status)
            assert status == db_entry.status, key

            if 'ackt' in data:
                ack_transient = data['ackt'] == 'YES'
                assert ack_transient == db_entry.alarm.must_acknowledge_transient

            if 'acks' in data:
                ack_severity = data['acks']
                ack_severity = getattr(ca._dbr.AlarmSeverity, ack_severity)
                assert ack_severity == db_entry.alarm.severity_to_acknowledge

        test_completed = True

    try:
        server(pvdb=caget_pvdb, client=client)
    except OSError:
        if sys.platform == 'win32' and test_completed:
            # WIN32_TODO: windows asyncio stuff is still buggy...
            ...
        else:
            raise

    print('done')


caput_checks = [('int', '1', 1),
                ('pi', '3.15', 3.15),
                ('enum', 'd', 'd'),
                ('enum2', 'cc', 'cc'),
                ('str', 'resolve', 'resolve'),
                ('char', '51', b'3'),
                ('chararray', 'testing', 'testing'),
                ('bytearray', 'testing', b'testing'),
                ('stra', ['char array'], ['char array']),
                ]


@pytest.mark.skipif(not has_caput(), reason='No caput binary')
@pytest.mark.parametrize('pv, put_value, check_value', caput_checks)
def test_with_caput(backends, prefix, pvdb_from_server_example, server, pv,
                    put_value, check_value):

    caget_pvdb = {prefix + pv_: value
                  for pv_, value in pvdb_from_server_example.items()
                  }
    pv = prefix + pv
    test_completed = False

    async def client(*client_args):
        nonlocal test_completed

        # args are ignored for curio and trio servers.
        print('* client put test: {} put value: {} check value: {}'
              ''.format(pv, put_value, check_value))
        print('(client args: {})'.format(client_args))

        db_entry = caget_pvdb[pv]
        db_old = db_entry.value
        data = await run_caput(server.backend, pv, put_value,
                               as_string=isinstance(db_entry, (ca.ChannelByte,
                                                               ca.ChannelChar)))
        db_new = db_entry.value

        clean_func = None
        if isinstance(db_entry, (ca.ChannelInteger, ca.ChannelDouble)):
            def clean_func(v):
                return ast.literal_eval(v)
        elif isinstance(db_entry, (ca.ChannelEnum, )):
            def clean_func(v):
                if ' ' not in v:
                    return v
                return v.split(' ', 1)[1]
        elif isinstance(db_entry, ca.ChannelByte):
            def clean_func(v):
                if pv.endswith('bytearray'):
                    return v.encode('latin-1')
                else:
                    return chr(int(v)).encode('latin-1')
        elif isinstance(db_entry, ca.ChannelChar):
            ...
        elif isinstance(db_entry, ca.ChannelString):
            if pv.endswith('stra'):
                # database holds ['char array'], caput shows [len char array]
                def clean_func(v):
                    return [v.split(' ', 1)[1]]

        if clean_func is not None:
            for key in ('old', 'new'):
                data[key] = clean_func(data[key])

        print('caput data', data)
        print('old from db', db_old)
        print('new from db', db_new)
        print('old from caput', data['old'])
        print('new from caput', data['new'])

        if isinstance(db_new, array_types):
            db_new = db_new.tolist()

        # check value from database compared to value from caput output
        assert db_new == data['new'], 'left = database/right = caput output'
        # check value from database compared to value the test expects
        assert db_new == check_value, 'left = database/right = test expected'

        test_completed = True

    try:
        server(pvdb=caget_pvdb, client=client)
    except OSError:
        if sys.platform == 'win32' and test_completed:
            # WIN32_TODO: windows asyncio stuff is still buggy...
            ...
        else:
            raise

    print('done')


def test_limits_enforced(request, caproto_ioc):
    pv = caproto_ioc.pvs['float']
    write(pv, 3.101, notify=True)  # within limit
    write(pv, 3.179, notify=True)  # within limit
    with pytest.raises(ErrorResponseReceived):
        write(pv, 3.09, notify=True)  # beyond limit
    with pytest.raises(ErrorResponseReceived):
        write(pv, 3.181, notify=True)  # beyond limit


def test_empties_with_caproto_client(request, caproto_ioc):
    assert read(caproto_ioc.pvs['empty_string']).data == [b'']
    assert list(read(caproto_ioc.pvs['empty_bytes']).data) == []
    assert list(read(caproto_ioc.pvs['empty_char']).data) == []
    assert list(read(caproto_ioc.pvs['empty_float']).data) == []


@pytest.mark.skipif(not has_caget(), reason='No caget binary')
def test_empties_with_caget(request, caproto_ioc):
    async def test():
        info = await run_caget('asyncio', caproto_ioc.pvs['empty_string'])
        assert info['value'] == ''

        info = await run_caget('asyncio', caproto_ioc.pvs['empty_bytes'])
        # NOTE: this zero is not a value, it's actually the length:
        # $ caget  type_varieties:empty_bytes
        # type_varieties:empty_bytes     0
        # $ caget -#0  type_varieties:empty_bytes
        # type_varieties:empty_bytes     0
        # $ caget -#1  type_varieties:empty_bytes
        # type_varieties:empty_bytes     1 0
        assert info['value'] == '0'

        info = await run_caget('asyncio', caproto_ioc.pvs['empty_char'])
        assert info['value'] == '0'

        info = await run_caget('asyncio', caproto_ioc.pvs['empty_float'])
        # NOTE: 2 below is length, with 2 elements of 0
        assert info['value'] == ['2', '0', '0']
        # TODO: somehow caget gets the max_length instead of the current
        # length.  caproto-get does not have this issue.

    asyncio.get_event_loop().run_until_complete(test())


def test_char_write(request, caproto_ioc):
    pv = caproto_ioc.pvs['chararray']
    write(pv, b'testtesttest', notify=True)
    response = read(pv)
    assert ''.join(chr(c) for c in response.data) == 'testtesttest'


@pytest.mark.parametrize('async_lib', ['asyncio', 'curio', 'trio'])
def test_write_without_notify(request, prefix, async_lib):
    pv = f'{prefix}pi'
    run_example_ioc('caproto.ioc_examples.type_varieties', request=request,
                    args=['--prefix', prefix, '--async-lib', async_lib],
                    pv_to_check=pv)
    write(pv, 3.179, notify=False)
    # We do not get notified so we have to poll for an update.
    for _attempt in range(20):
        if read(pv).data[0] > 3.178:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Server never processed WriteRequest.")


@pytest.mark.parametrize(
    'cls, kwargs',
    [(ca.ChannelAlarm, {}),
     (ca.ChannelData, {}),
     (ca.ChannelByte, {'value': b'b'}),
     (ca.ChannelChar, {'value': 'b', 'string_encoding': 'latin-1'}),
     (ca.ChannelDouble, {'value': 0.1}),
     (ca.ChannelEnum, {'value': 'a', 'string_encoding': 'latin-1',
                       'enum_strings': ['a', 'b', 'c']}),
     (ca.ChannelInteger, {'value': 5}),
     (ca.ChannelNumeric, {'value': 5}),
     (ca.ChannelShort, {'value': 5}),
     (ca.ChannelString, {'value': 'abcd'}),
     ]
)
def test_data_copy(cls, kwargs):
    inst1 = cls(**kwargs)
    _, args1 = inst1.__getnewargs_ex__()

    inst2 = copy.deepcopy(inst1)
    _, args2 = inst2.__getnewargs_ex__()

    def patch_alarm(args):
        if 'alarm' in args:
            args['alarm'] = args['alarm'].__getnewargs_ex__()

    patch_alarm(args1)
    patch_alarm(args2)
    assert args1 == args2


@pytest.mark.parametrize('async_lib', ['asyncio', 'curio', 'trio'])
def test_process_field(request, prefix, async_lib):
    run_example_ioc('caproto.tests.ioc_process', request=request,
                    args=['--prefix', prefix, '--async-lib', async_lib],
                    pv_to_check=f'{prefix}record.PROC')

    write(f'{prefix}record.PROC', [1], notify=True)
    write(f'{prefix}record.PROC', [1], notify=True)
    assert read(f'{prefix}count').data[0] == 2
