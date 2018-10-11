'''
Helper functions for dealing with EPICS base binaries (caget, caput, catest)
'''

import os
import sys
import datetime
import subprocess

import asyncio
import curio
import curio.subprocess

import trio

import caproto as ca


async def run_epics_base_binary(backend, *args, max_attempts=3):
    '''Run an EPICS-base binary with the environment variables set

    Returns
    -------
    stdout, stderr
        Decoded standard output and standard error text
    '''
    if sys.platform == 'win32':
        args = list(args)
    else:
        args = ['/usr/bin/env'] + list(args)

    print()
    print('* Executing', args)

    epics_env = ca.get_environment_variables()
    env = os.environ.copy()
    env.update(PATH=os.environ['PATH'],
               EPICS_CA_AUTO_ADDR_LIST=epics_env['EPICS_CA_AUTO_ADDR_LIST'],
               EPICS_CA_ADDR_LIST=epics_env['EPICS_CA_ADDR_LIST'])

    def runner(attempt=0):
        e = os.environ.copy()
        e.update(env)
        with subprocess.Popen(args, env=e, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as proc:
            raw_stdout, raw_stderr = proc.communicate()

        if b'Channel connect timeout' in raw_stderr:
            attempt += 1

            if attempt < max_attempts:
                return runner(attempt=attempt + 1)
        return raw_stdout, raw_stderr

    if backend == 'curio':
        raw_stdout, raw_stderr = await curio.run_in_thread(runner)
    elif backend == 'trio':
        raw_stdout, raw_stderr = await trio.run_sync_in_worker_thread(runner)
    elif backend == 'asyncio':
        loop = asyncio.get_event_loop()
        raw_stdout, raw_stderr = await loop.run_in_executor(None, runner)
    else:
        raise NotImplementedError('Unsupported async backend')

    stdout = raw_stdout.decode('latin-1')
    stderr = raw_stderr.decode('latin-1')
    return stdout, stderr


async def run_caget(backend, pv, *, dbr_type=None):
    '''Execute epics-base caget and parse results into a dictionary

    Parameters
    ----------
    pv : str
        PV name
    dbr_type : caproto.ChannelType, optional
        Specific dbr_type to request
    '''
    sep = '@'
    args = ['caget', '-F', sep,
            '-w', '1.0',
            ]

    if dbr_type is None:
        args += ['-a']
        wide_mode = True
    else:
        dbr_type = int(dbr_type)
        args += ['-d', str(dbr_type)]
        wide_mode = False
    args.append(pv)

    output, stderr = await run_epics_base_binary(backend, *args)

    print('----------------------------------------------------------')
    print(output)
    print()

    key_map = {
        'Native data type': 'native_data_type',
        'Request type': 'request_type',
        'Element count': 'element_count',
        'Value': 'value',
        'Status': 'status',
        'Severity': 'severity',
        'Units': 'units',
        'Lo disp limit': 'lower_disp_limit',
        'Hi disp limit': 'upper_disp_limit',
        'Lo alarm limit': 'lower_alarm_limit',
        'Lo warn limit': 'lower_warning_limit',
        'Hi warn limit': 'upper_warning_limit',
        'Hi alarm limit': 'upper_alarm_limit',
        'Lo ctrl limit': 'lower_ctrl_limit',
        'Hi ctrl limit': 'upper_ctrl_limit',
        'Timestamp': 'timestamp',
        'Precision': 'precision',
        'Enums': 'enums',
        'Class Name': 'class_name',
        'Ack transient?': 'ackt',
        'Ack severity': 'acks',
    }

    lines = [line.strip() for line in output.split('\n')
             if line.strip()]

    if not lines:
        raise RuntimeError('caget failed: {}'.format(stderr))

    if wide_mode:
        print('lines')
        print(lines[0].split(sep))
        pv, timestamp, value, stat, sevr = lines[0].split(sep)
        info = dict(pv=pv,
                    timestamp=timestamp,
                    value=value,
                    status=stat,
                    severity=sevr)
    else:
        info = dict(pv=lines[0])
        in_enum_section = False
        enums = {}
        for line in lines[1:]:
            if line:
                if in_enum_section:
                    num, name = line.split(']', 1)
                    num = int(num[1:])
                    enums[num] = name.strip()
                else:
                    key, value = line.split(':', 1)
                    info[key_map[key]] = value.strip()

                    if key == 'Enums':
                        in_enum_section = True
        if enums:
            info['enums'] = enums

    if 'timestamp' in info:
        if info['timestamp'] != '<undefined>':
            info['timestamp'] = datetime.datetime.strptime(
                info['timestamp'], '%Y-%m-%d %H:%M:%S.%f')

    return info


async def run_catest(backend, pv, *, dbr_type=None):
    '''Execute epics-base ca_test and parse results into a dictionary

    Parameters
    ----------
    pv : str
        PV name
    '''
    output, stderr = await run_epics_base_binary(backend, 'ca_test', pv)

    print('----------------------------------------------------------')

    lines = []
    line_starters = ['name:', 'native type:', 'native count:']
    for line in output.split('\n'):
        line = line.rstrip()
        if line.startswith('DBR'):
            lines.append(line)
        else:
            if any(line.startswith(starter) for starter in line_starters):
                lines.append(line)
            else:
                lines[-1] += line

    return lines


async def run_caput(backend, pv, value, *, async_put=True, as_string=False):
    '''Execute epics-base caput and parse results into a dictionary

    Parameters
    ----------
    pv : str
        PV name
    value : str
        Value to put
    async_put : bool, optional
        Use asynchronous put method (-c)
    as_string : bool, optional
        Put string as an array of chars
    '''

    args = ['caput',
            '-' + (('c' if async_put else '') +
                   ('S' if as_string else '') +
                   'w'),
            '1.0',
            pv]

    if isinstance(value, (list, tuple)):
        args.extend(list(value))
    else:
        args.append(value)
    print(args)
    output, stderr = await run_epics_base_binary(backend, *args)

    print('----------------------------------------------------------')
    print(output)
    print()

    lines = [line.strip() for line in output.split('\n')
             if line.strip()]

    if not lines:
        raise RuntimeError('caput failed: {}'.format(stderr))

    info = {}
    for line in lines:
        # Old : pv (count) (values)
        # New : pv (count) (values)
        if line.startswith('Old :') or line.startswith('New : '):
            key, _, pv, value = line.split(' ', 3)
            key = line.split(' ', 1)[0].lower()
            info['pv'] = pv
            info[key] = value.strip()

    return info
