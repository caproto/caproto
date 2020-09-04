import datetime
import linecache
import logging
import os
import platform
import sys
import tracemalloc
import typing

from .. import ChannelType, __version__
from . import PVGroup, pvproperty
from .autosave import autosaved

MODULE_LOGGER = logging.getLogger(__name__)


def get_top_allocation_info(snapshot: tracemalloc.Snapshot, *,
                            key_type: str = 'lineno',
                            limit: int = 10
                            ) -> typing.List[str]:
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
        tracemalloc.Filter(False, "<tracemalloc>"),
    ))
    top_stats = snapshot.statistics(key_type)

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


class StatusHelper(PVGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._root_pvgroup = self._find_top_level_pvgroup()
        self._old_snapshot = None

    def _find_top_level_pvgroup(self):
        ancestor = self.parent
        while ancestor.parent is not None:
            ancestor = ancestor.parent
        return ancestor

    access = pvproperty(
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

    tod = pvproperty(
        value='',
        name='TOD',
        max_length=100,
        record='stringin',
        doc="Current time and date",
        read_only=True
    )

    @tod.scan(period=1)
    async def tod(self, instance, async_lib):
        await self.tod.write(value=str(datetime.datetime.now()))

    heartbeat = pvproperty(
        value=0,
        name='HEARTBEAT',
        record='calcout',
        doc='1 Hz counter since startup',
        read_only=True,
    )

    @heartbeat.scan(period=1)
    async def heartbeat(self, instance, async_lib):
        await self.heartbeat.write(value=1 - self.heartbeat.value)

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

    sysreset = pvproperty(
        name='SYSRESET',
        record='sub',
        doc='IOC Restart',
    )

    @sysreset.putter
    async def sysreset(self, instance, value):
        if value == 1:
            sys.exit(0)

    # TODO: any way we can find this information?
    # ca_client_count = pvproperty(
    #     value=0,
    #     name='CA_CLNT_CNT',
    #     record='longin',
    #     read_only=True,
    #     doc='Number of CA clients',
    # )

    # ca_connection_count = pvproperty(
    #     value=0,
    #     name='CA_CONN_CNT',
    #     record='longin',
    #     read_only=True,
    #     doc='Number of CA Connections',
    # )

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
        # TODO: linux use /proc/self/fd
        value=0,
        doc='Allocated File Descriptors',
        name='FD_CNT',
        record='ai',
        read_only=True,
    )

    fd_free = pvproperty(
        # TODO: (fd_max - fd_count)
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
        doc='Number of Suspended Tasks',
    )

    mem_used = pvproperty(
        value=0,
        name='MEM_USED',
        record='ai',
        units='byte',
        read_only=True,
    )

    mem_free = pvproperty(
        value=0,
        name='MEM_FREE',
        record='ai',
        units='byte',
        read_only=True,
    )

    mem_max = pvproperty(
        value=0,
        name='MEM_MAX',
        record='ai',
        units='byte',
        read_only=True,
    )

    uptime = pvproperty(
        value=0,
        name='UPTIME',
        record='stringin',
        units='s',
        doc='Elapsed time since start',
        read_only=True,
    )

    hostname = pvproperty(
        value='',
        name='HOSTNAME',
        record='stringin',
        read_only=True,
    )

    app_dir = pvproperty(
        value='',
        name='APP_DIR',
        record='waveform',
        max_length=255,
        read_only=True,
        doc='Script directory',
    )

    # The following only update once:
    engineer = pvproperty(
        value='',
        name='ENGINEER',
        record='stringin',
        read_only=True,
    )

    location = pvproperty(
        value='',
        name='LOCATION',
        record='stringin',
        read_only=True,
    )

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
        value='',
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

    async def _update_one_time_only_values(self):
        await self.process_id.write(os.getpid())
        await self.parent_pid.write(os.getppid())
        await self.location.write(os.environ.get('LOCATION', ''))
        await self.engineer.write(os.environ.get('ENGINEER', ''))
        await self.kernel_version.write(platform.uname().version)

        try:
            # This is standard library, but I'm unsure if it's included on
            # windows:
            import resource  # noqa
            soft_limit, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        except OSError:
            ...
        else:
            await self.fd_max.write(soft_limit)

    update_period = pvproperty(
        value=15.0,
        name='UPD_TIME',
        record='ao',
        lower_ctrl_limit=1,
        upper_ctrl_limit=60,
        doc='Basic stats update rate',
    )

    async def _update_status_periodic(self):
        if self._root_pvgroup is None:
            return
        await self.record_count.write(value=len(self._root_pvgroup.pvdb))

    @update_period.startup
    async def update_period(self, instance, async_lib):
        await self._update_one_time_only_values()
        while True:
            try:
                await self._update_status_periodic()
            except Exception as ex:
                self.log.warning('Status update failure: %s', ex)
            await async_lib.library.sleep(self.update_period.value)

    enable_tracing = pvproperty(
        name='EnableTracing',
        # value='Disable',
        value='Enable',
        doc='Enable/disable in-depth memory analysis',
        record='bo',
        enum_strings=['Disable', 'Enable'],
        dtype=ChannelType.ENUM,
    )

    trace_diff_results = pvproperty(
        name='TraceDiffResults',
        value='Unset',
        max_length=20000,
        read_only=True,
        doc='',
        record='waveform',
    )

    top_allocations = pvproperty(
        name='TraceTopAllocations',
        value='Unset',
        max_length=20000,
        read_only=True,
        doc='',
        record='waveform',
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

        top_lines, stats = get_top_allocation_info(snapshot)

        await self.top_allocations.write(
            '\n'.join(top_lines)[:self.top_allocations.max_length]
        )
        await self.mem_used.write(sum(stat.size for stat in stats))

        if self._old_snapshot is not None:
            comparison = snapshot.compare_to(self._old_snapshot, 'lineno')

            self.log.debug('** %s **', datetime.datetime.now())
            for stat in comparison[:10]:
                self.log.debug(stat)

            status = '\n'.join(str(stat) for stat in comparison[:10])
            await self.trace_diff_results.write(
                status[:self.trace_diff_results.max_length])

        self._old_snapshot = snapshot
