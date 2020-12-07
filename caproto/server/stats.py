import datetime
import inspect
import linecache
import logging
import os
import pathlib
import platform
import sys
import threading
import tracemalloc
import typing
from typing import List, Optional

from .. import ChannelType, __version__
from . import PVGroup, SubGroup, pvproperty
from .autosave import autosaved

try:
    import psutil
except ImportError:
    psutil = None

try:
    # This is part of the standard library, but I'm unsure if it's
    # included on windows:
    import resource
except ImportError:
    resource = None


MODULE_LOGGER = logging.getLogger(__name__)


def _find_top_level_pvgroup(group: PVGroup) -> PVGroup:
    ancestor = group
    while ancestor.parent is not None:
        ancestor = ancestor.parent
    return ancestor


def get_source_file(obj: typing.Any) -> pathlib.Path:
    """Get the source filename of `obj` as a :class:`~pathlib.Path`."""
    return pathlib.Path(inspect.getsourcefile(obj)).resolve()


class BasicStatusHelper(PVGroup):
    _root_pvgroup: PVGroup

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._root_pvgroup = _find_top_level_pvgroup(self)

    process_id = pvproperty(
        value=0,
        name='PROCESS_ID',
        record='ai',
        read_only=True,
    )

    parent_pid = pvproperty(
        name='PARENT_ID',
        record='ai',
        doc="Parent Process ID",
        read_only=True,
    )

    cpu_count = pvproperty(
        value=0,
        name='CPU_CNT',
        record='longin',
        read_only=True,
        doc='Number of CPUs',
    )

    kernel_version = pvproperty(
        value=str(platform.uname().version),
        name='KERNEL_VERS',
        record='stringin',
        doc='OS/Kernel Version',
        read_only=True,
    )

    version = pvproperty(
        value=f'{__version__} on {sys.version}',
        name='EPICS_VERSION',
        record='stringin',
        doc='EPICS (caproto) version',
        read_only=True,
    )

    engineer = pvproperty(
        value='',
        max_length=40,
        name='ENGINEER',
        record='stringin',
        read_only=True,
        doc='Who is responsible for this abomination',
    )

    location = pvproperty(
        value='',
        max_length=40,
        name='LOCATION',
        record='stringin',
        read_only=True,
    )

    hostname = pvproperty(
        value='',
        max_length=255,
        name='HOSTNAME',
        record='stringin',
        read_only=True,
    )

    application_directory = pvproperty(
        value='',
        name='APP_DIR',
        record='waveform',
        max_length=255,
        read_only=True,
        doc='Startup directory (__main__)',
    )

    source_filename = pvproperty(
        value='',
        name='SOURCE_FILE',
        record='waveform',
        max_length=255,
        read_only=True,
        doc='Top-level PVGroup source filename',
    )

    sysreset = pvproperty(
        name='SYSRESET',
        record='sub',
        doc='IOC exit / restart (if using procServ)',
    )

    @sysreset.putter
    async def sysreset(self, instance, value):
        if value == 1:
            self.log.warning('Exit requested using StatusHelper!')
            sys.exit(0)

    @process_id.startup
    async def process_id(self, instance, async_lib):
        await self.process_id.write(value=os.getpid())
        await self.parent_pid.write(value=os.getppid())
        await self.location.write(value=os.environ.get('LOCATION', ''))
        await self.engineer.write(value=os.environ.get('ENGINEER', ''))

        try:
            root_source = get_source_file(type(self._root_pvgroup))
            await self.source_filename.write(value=str(root_source))
        except Exception:
            self.log.exception('Unable to determine source path')

        try:
            main_path = get_source_file(sys.modules['__main__'])
            await self.application_directory.write(value=str(main_path.parent))
        except TypeError:
            # Built-in is OK
            ...
        except Exception:
            self.log.exception('Unable to determine startup directory')

        if psutil is not None:
            await self.cpu_count.write(value=psutil.cpu_count())


class PeriodicStatusHelper(PVGroup):
    """
    An IocStats-like tool for caproto IOCs.  Includes values which update
    on a periodic basis (:attr:`update_period`, PV ``UPD_TIME``).
    """

    _process: Optional['psutil.Process']
    _root_pvgroup: PVGroup

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._root_pvgroup = _find_top_level_pvgroup(self)
        self._process = None

        if psutil is None:
            self.log.warning(
                "The Python library psutil is not installed, so MEM_USED will "
                "not be reported by StatsHelper."
            )
        else:
            self._process = psutil.Process()

    access = pvproperty(
        # Not implemented:
        name='ACCESS',
        doc='CA Security access level to this IOC',
        enum_strings=['Running', 'Maintenance', 'Test', 'OFFLINE'],
        record='mbbo',
        value='Running',
        dtype=ChannelType.ENUM,
    )

    start_tod = pvproperty(
        value='',
        max_length=100,
        name='STARTTOD',
        record='stringin',
        doc="Time and date of startup",
        read_only=True,
    )

    @start_tod.startup
    async def start_tod(self, instance, async_lib):
        await self.start_tod.write(value=str(datetime.datetime.now()))

    time_of_day = pvproperty(
        value='',
        name='TOD',
        max_length=100,
        record='stringin',
        doc="Current time and date",
        read_only=True
    )

    @time_of_day.scan(period=1)
    async def time_of_day(self, instance, async_lib):
        """Update time-of-day."""
        await self.time_of_day.write(value=str(datetime.datetime.now()))

    heartbeat = pvproperty(
        value=0,
        name='HEARTBEAT',
        record='calcout',
        doc='1 Hz counter since startup',
        read_only=True,
    )

    @heartbeat.scan(period=1)
    async def heartbeat(self, instance, async_lib):
        next_beat = (self.heartbeat.value + 1) % (2 ** 31)
        await self.heartbeat.write(value=next_beat)

    start_count = pvproperty(
        value=0,
        name='START_CNT',
        record='calcout',
        doc='Startup count, if autosave is working',
        read_only=True,
    )
    autosaved(start_count)

    @start_count.startup
    async def start_count(self, instance, async_lib):
        # Give autosave some time to load
        await async_lib.library.sleep(3)
        await self.start_count.write(value=self.start_count.value + 1)

    # TODO: any way we can find this information?
    ca_client_count = pvproperty(
        value=0,
        name='CA_CLNT_CNT',
        record='longin',
        read_only=True,
        doc='Number of CA clients [not implemented]',
    )

    ca_connection_count = pvproperty(
        value=0,
        name='CA_CONN_CNT',
        record='longin',
        read_only=True,
        doc='Number of CA Connections [not implemented]',
    )

    record_count = pvproperty(
        name='RECORD_CNT',
        record='ai',
        read_only=True,
        doc='Number of records',
    )

    fd_max = pvproperty(
        value=0,
        name='FD_MAX',
        record='ai',
        doc='Max File Descriptors',
        read_only=True,
    )

    fd_count = pvproperty(
        value=0,
        doc='Allocated File Descriptors',
        name='FD_CNT',
        record='ai',
        read_only=True,
    )

    fd_free = pvproperty(
        name='FD_FREE',
        record='calc',
        read_only=True,
        doc='Available FDs',
    )

    sys_cpu_load = pvproperty(
        value=0.0,
        name='SYS_CPU_LOAD',
        record='ai',
        lower_ctrl_limit=0.0,
        upper_ctrl_limit=100.0,
        units='%',
        read_only=True,
        doc='CPU load',
    )

    ioc_cpu_load = pvproperty(
        value=0.0,
        name='IOC_CPU_LOAD',
        record='ai',
        lower_ctrl_limit=0.0,
        upper_ctrl_limit=100.0,
        units='%',
        read_only=True,
    )

    susp_task_count = pvproperty(
        value=0,
        name='SUSP_TASK_CNT',
        record='longin',
        read_only=True,
        doc='Number of Suspended Tasks [not implemented]',
    )

    mem_used = pvproperty(
        value=0,
        name='MEM_USED',
        record='ai',
        units='KByte',
        read_only=True,
        doc='Memory used.',
    )

    mem_free = pvproperty(
        value=0,
        name='MEM_FREE',
        record='ai',
        units='KByte',
        read_only=True,
        doc='Memory free (including swap).',
    )

    mem_max = pvproperty(
        value=0,
        name='MEM_MAX',
        record='ai',
        units='KByte',
        read_only=True,
    )

    uptime = pvproperty(
        value=0,
        name='UPTIME',
        record='longin',
        units='s',
        doc='Elapsed time since start',
        read_only=True,
    )

    num_threads = pvproperty(
        value=0,
        name='NumThreads',
        record='longin',
        read_only=True,
        doc='Number of threads in use',
    )

    update_period = pvproperty(
        value=15.0,
        name='UPD_TIME',
        record='ao',
        lower_ctrl_limit=1,
        upper_ctrl_limit=60,
        doc='Basic stats update rate',
    )

    async def _update_psutil_status(self):
        """Update process information, if psutil is available."""
        if self._process is None:
            return

        process = typing.cast(psutil.Process, self._process)

        # Memory usage
        memory_info = process.memory_info()
        await self.mem_used.write(value=memory_info.rss // 1024)

        # Memory available
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        await self.mem_free.write(value=(vmem.available + swap.free) // 1024)
        await self.mem_max.write(value=(vmem.total + swap.total) // 1024)

        # CPU usage
        await self.ioc_cpu_load.write(value=process.cpu_percent())
        await self.sys_cpu_load.write(value=psutil.cpu_percent())

        # File descriptor information:
        await self.fd_count.write(value=process.num_fds())
        await self.fd_free.write(value=self.fd_max.value - self.fd_count.value)

    async def _update(self):
        """Periodic updates happen here."""
        await self.record_count.write(value=len(self._root_pvgroup.pvdb))
        await self._update_psutil_status()

        await self.num_threads.write(value=threading.active_count())

        # Uptime since our startup method was first called:
        elapsed = datetime.datetime.now() - self._startup_time
        await self.uptime.write(value=elapsed.total_seconds())

    @update_period.startup
    async def update_period(self, instance, async_lib):
        self._startup_time = datetime.datetime.now()
        if resource is not None:
            try:
                soft_limit, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                await self.fd_max.write(value=soft_limit)
            except Exception:
                self.log.warning('Failed to get maximum file descriptors')

        while True:
            try:
                await self._update()
            except Exception as ex:
                self.log.warning('Status update failure: %s', ex)
            await async_lib.library.sleep(self.update_period.value)


TRACEMALLOC_FILTERS = (
    tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
    tracemalloc.Filter(False, "<unknown>"),
    tracemalloc.Filter(False, tracemalloc.__file__),
)


def get_top_allocation_info(snapshot: tracemalloc.Snapshot, *,
                            key_type: str = 'lineno',
                            cumulative: bool = False,
                            limit: int = 20,
                            filters: Optional[List[tracemalloc.Filter]] = None,
                            ) -> List[str]:
    """
    Get the top allocations from a given tracemalloc snapshot in a list.

    Parameters
    ----------
    snapshot : tracemalloc.Snapshot
        Snapshot to get information from.
    key_type : str, optional
        Key for the snapshot statistics.
    cumulative : bool, optional
        Cumulative statistics.
    limit : int, optional
        Limit the number of results.
    filters : list of tracemalloc.Filter
        Filters to apply to the snapshot.

    Returns
    -------
    text_lines : list of str
    """
    if filters is None:
        filters = TRACEMALLOC_FILTERS

    snapshot = snapshot.filter_traces(filters)
    top_stats = snapshot.statistics(key_type, cumulative=cumulative)

    result = []
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        kbytes = stat.size / 1024
        result.append(
            f"#{index}: {frame.filename}:{frame.lineno}: {kbytes:.1f} KiB"
        )
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            result.append(f'    {line}')

    return result, top_stats


class MemoryTracingHelper(PVGroup):
    """
    A helper which quickly allows for tracing memory usage and allocations on a
    caproto server instance.

    Parameters
    ----------
    prefix : str
        Prefix for all PVs in the group
    macros : dict, optional
        Dictionary of macro name to value
    parent : PVGroup, optional
        Parent PVGroup
    name : str, optional
        Name for the group, defaults to the class name
    states : dict, optional
        A dictionary of states used for channel filtering. See
        https://epics.anl.gov/base/R3-15/5-docs/filters.html
    filters : list of tracemalloc.Filter, optional
        Filters to apply to the snapshot.  Defaults to TRACEMALLOC_FILTERS.
    """
    _old_snapshot: tracemalloc.Snapshot
    filters: List[tracemalloc.Filter]

    def __init__(self, *args,
                 filters: Optional[List[tracemalloc.Filter]] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._old_snapshot = None
        if filters is None:
            filters = TRACEMALLOC_FILTERS
        self.filters = filters

    enable_tracing = pvproperty(
        name='EnableTracing',
        value='Disable',
        doc='Enable/disable in-depth memory analysis',
        record='bo',
        enum_strings=['Disable', 'Enable'],
        dtype=ChannelType.ENUM,
    )

    diff_results = pvproperty(
        name='TraceDiffResults',
        value='Unset',
        max_length=20000,
        read_only=True,
        doc='Trace diff from snapshot to snapshot',
        record='waveform',
    )

    top_allocations = pvproperty(
        name='TraceTopAllocations',
        value='Unset',
        max_length=20000,
        read_only=True,
        doc='Top allocations in snapshot',
        record='waveform',
    )

    trace_count = pvproperty(
        name='TraceCount',
        value=10,
        read_only=False,
        doc='Number of top allocations to view',
        record='ao',
    )

    @enable_tracing.scan(period=10)
    async def enable_tracing(self, instance, async_lib):
        if self.enable_tracing.value == 'Disable':
            if tracemalloc.is_tracing():
                self._old_snapshot = None
                tracemalloc.stop()
            return

        if not tracemalloc.is_tracing():
            tracemalloc.start()

        snapshot = tracemalloc.take_snapshot()
        count = self.trace_count.value
        top_lines, stats = get_top_allocation_info(snapshot, limit=count)

        await self.top_allocations.write(
            value='\n'.join(top_lines)[:self.top_allocations.max_length]
        )

        if self._old_snapshot is not None:
            comparison = snapshot.filter_traces(
                self.filters
            ).compare_to(self._old_snapshot, 'lineno')

            self.log.debug('** %s **', datetime.datetime.now())
            for stat in comparison[:count]:
                self.log.debug(stat)

            status = '\n'.join(str(stat) for stat in comparison[:count])
            await self.diff_results.write(
                value=status[:self.diff_results.max_length]
            )

        self._old_snapshot = snapshot


class StatusHelper(PVGroup):
    """
    An IocStats-like tool for caproto IOCs.

    Includes all PVs from :class:`BasicStatusHelper` and
    :class:`PeriodicStatusHelper`.
    """
    basic = SubGroup(BasicStatusHelper, prefix='')
    periodic = SubGroup(PeriodicStatusHelper, prefix='')
