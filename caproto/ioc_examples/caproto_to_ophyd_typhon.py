import os
import sys
import time
import logging
import random

import ophyd
from ophyd import Component as Cpt, EpicsSignal

from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.curio.high_level_server import (pvproperty, PVGroup,
                                             pvfunction)


logger = logging.getLogger(__name__)


# Step 1: a caproto high-level server

class Group(PVGroup):
    'Example group of PVs, where the prefix is defined on instantiation'
    async def _exit(self, instance, value):
        logger.info('Server shutting down')
        sys.exit(0)

    exit = pvproperty(put=_exit, doc='Poke me to exit')

    @pvproperty
    async def random1(self, instance):
        'Random integer between 1 and 100'
        return random.randint(1, 100)

    @pvproperty
    async def random2(self, instance):
        'A nice random integer between 1000 and 2000'
        return random.randint(1000, 2000)

    @pvfunction(default=[0])
    async def get_random(self,
                         low: int=100,
                         high: int=1000) -> int:
        'A configurable random number'
        low, high = low[0], high[0]
        return random.randint(low, high)


# Step 2a: supporting methods to make simple ophyd Devices
def pvfunction_to_device_function(name, pvf, *, indent='    '):
    def format_arg(pvspec):
        value = pvspec.value
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        value = f'={value}' if value else ''
        return f"{pvspec.attr}: {pvspec.dtype.__name__}{value}"

    skip_attrs = ('Status', 'Retval')
    args = ', '.join(format_arg(spec) for spec in pvf.pvspec
                     if spec.attr not in skip_attrs)
    yield f"{indent}def call(self, {args}):"
    if pvf.__doc__:
        yield f"{indent*2}'{pvf.__doc__}'"
    for pvspec in pvf.pvspec:
        if pvspec.attr not in skip_attrs:
            yield (f"{indent*2}self.{pvspec.attr}.put({pvspec.attr}, "
                   "wait=True)")

    yield f"{indent*2}self.process.put(1, wait=True)"
    yield f"{indent*2}status = self.status.get(use_monitor=False)"
    yield f"{indent*2}retval = self.retval.get(use_monitor=False)"
    yield f"{indent*2}if status != 'Success':"
    yield f"{indent*3}raise RuntimeError(f'RPC function failed: {{status}}')"
    yield f"{indent*2}return retval"


def group_to_device(group):
    'Make an ophyd device from a high-level server PVGroup'
    # TODO subgroups are weak and need rethinking (generic comment deux)

    for name, subgroup in group._subgroups_.items():
        yield from group_to_device(subgroup.group_cls)

        if isinstance(subgroup, pvfunction):
            yield f''
            yield from pvfunction_to_device_function(name, subgroup)

        yield f''
        yield f''

    if isinstance(group, PVGroup):
        group = group.__class__

    yield f"class {group.__name__}Device(ophyd.Device):"

    for name, subgroup in group._subgroups_.items():
        doc = f', doc={subgroup.__doc__!r}' if subgroup.__doc__ else ''
        yield (f"    {name.lower()} = Cpt({name}Device, "
               f"'{subgroup.prefix}'{doc})")

    if not group._pvs_:
        yield f'    ...'

    for name, prop in group._pvs_.items():
        if '.' in name:
            # Skipping, part of subgroup handled above
            continue

        pvspec = prop.pvspec
        doc = f', doc={pvspec.doc!r}' if pvspec.doc else ''
        string = f', string=True' if pvspec.dtype == str else ''
        yield (f"    {name.lower()} = Cpt(EpicsSignal, '{pvspec.name}'"
               f"{string}{doc})")
        # TODO will break when full/macro-ified PVs is specified

    # lower_name = group.__name__.lower()
    # yield f"# {lower_name} = {group.__name__}Device(my_prefix)"


# Step 2b: copy/pasting the auto-generated output (OK, slightly modified for
#                                                  PEP8 readability)

# Auto-generated Device from here on:
# -----------------------------------
class get_randomDevice(ophyd.Device):
    low = Cpt(EpicsSignal, 'low', doc="Parameter <class 'int'> low")
    high = Cpt(EpicsSignal, 'high', doc="Parameter <class 'int'> high")
    status = Cpt(EpicsSignal, 'Status', string=True, doc="Parameter <class 'str'> Status")
    retval = Cpt(EpicsSignal, 'Retval', doc="Parameter <class 'int'> Retval")
    process = Cpt(EpicsSignal, 'Process', doc="Parameter <class 'int'> Process")

    def call(self, low: int=100, high: int=1000):
        'A configurable random number'
        self.low.put(low, wait=True)
        self.high.put(high, wait=True)
        self.process.put(1, wait=True)
        status = self.status.get(use_monitor=False)
        retval = self.retval.get(use_monitor=False)
        if status != 'Success':
            raise RuntimeError(f'RPC function failed: {status}')
        return retval


class GroupDevice(ophyd.Device):
    get_random = Cpt(get_randomDevice, 'get_random:',
                     doc='A configurable random number')
    exit = Cpt(EpicsSignal, 'exit', doc='Poke me to exit')
    random1 = Cpt(EpicsSignal, 'random1',
                  doc='Random integer between 1 and 100')
    random2 = Cpt(EpicsSignal, 'random2',
                  doc='A nice random integer between 1000 and 2000')

# -------end autogenerated Devices---


if __name__ == '__main__':
    import curio

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'integration:'

    ioc = Group(prefix=prefix, macros={})

    print('import ophyd')
    print('from ophyd import Component as Cpt, EpicsSignal')

    print('# Auto-generated Device from here on:')
    print('# -----------------------------------')

    for line in group_to_device(ioc):
        print(line)

    print('# -----------------------------------')

    # Step 3 (a - parent, b - child)
    if os.fork():
        # Step 3a: Run the server in the parent process

        set_logging_level(logging.INFO)
        logger.setLevel(logging.INFO)
        logging.basicConfig()

        logger.info('Starting up: prefix=%r', prefix)

        curio.run(start_server, ioc.pvdb)
    else:
        # Step 3b: And the ophyd client in the child process :)
        dev = GroupDevice(prefix=prefix, name='dev')
        print(dev, dev.read_attrs)
        dev.wait_for_connection()
        get_value = dev.get()

        print('Current values are:')
        print(get_value)
        time.sleep(4)

        # Step 4 make a GUI in a line or two
        import pydm
        from typhon import DeviceDisplay
        app = pydm.PyDMApplication()
        typhon_display = DeviceDisplay(dev)
        typhon_display.method_panel.add_method(dev.get_random.call)
        typhon_display.show()
        app.exec_()
