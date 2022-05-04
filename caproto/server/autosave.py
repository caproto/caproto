import datetime
import json
import logging
import operator
import pathlib
import tempfile
import typing

from . import PVGroup, pvproperty

MODULE_LOGGER = logging.getLogger(__name__)


class RotatingFileManager:
    """
    Save to a primary filename, while rotating out old copies.

    Automatically prunes old copies of the file beyond a certain age or a
    maximum file count (overall or per day).

    Files will first be pruned by the overall age cutoff, then on a per day
    basis.

    Parameters
    ----------
    filename : str
        The primary filename that should be used.

    max_files_per_day : int, optional
        Remove the oldest files in a given day.

    max_file_age : int, optional
        Prune files beyond this cutoff.

    date_suffix : str, optional
        Defaults to "_%Y%m%d-%H%M%S" - used by strftime/strptime.

    logger : logging.Logger, optional
        The logger instance to use for messages.  Defaults to the module
        logger.
    """

    date_suffix: str
    filename: pathlib.Path
    log: logging.Logger

    max_file_age: int
    max_files_per_day: int

    def __init__(self, filename, *, max_files_per_day=5, max_file_age=30,
                 date_suffix="_%Y%m%d-%H%M%S",
                 logger=MODULE_LOGGER):
        self.log = logger
        self.date_suffix = date_suffix
        self.filename = pathlib.Path(filename)
        self.max_files_per_day = max_files_per_day
        self.max_file_age = max_file_age
        self._date_format = ''.join((self.filename.stem,
                                     self.date_suffix,
                                     self.filename.suffix,
                                     ))
        self.files = self._get_file_dictionary()

    def _filename_to_date(self, fn: pathlib.Path
                          ) -> typing.Optional[datetime.datetime]:
        """Using the date format, determine the date of a file."""
        try:
            return datetime.datetime.strptime(fn.name, self._date_format)
        except ValueError:
            ...

    def _get_file_dictionary(self) -> typing.Dict[pathlib.Path,
                                                  datetime.datetime]:
        """Get {filename: datetime} dictionary of existing files."""
        files_and_dates = [
            (fn, self._filename_to_date(fn))
            for fn in self.directory.glob(self.glob_string)
            if fn != self.filename
        ]
        return {
            fn: dt for fn, dt in files_and_dates
            if dt is not None
        }

    @property
    def directory(self) -> pathlib.Path:
        """The directory holding the save file."""
        return self.filename.parent

    @property
    def glob_string(self) -> str:
        """The glob string which can be used to find matching files."""
        return f'{self.filename.stem}*{self.filename.suffix}'

    @property
    def files_by_age(self) -> typing.Dict[datetime.timedelta, pathlib.Path]:
        """Get a dictionary of {age_timedelta: filename}."""
        now = datetime.datetime.now()
        return {
            (now - file_date).seconds: fn
            for fn, file_date in self.files.items()
        }

    def prune_files(self) -> set:
        """
        Prune files that are outside of the configured maximum times.

        Returns
        -------
        pruned : set
            The set of pruned files.
        """
        files = self.files_by_age
        if not files:
            return set()

        seconds_per_day = 24 * 60 * 60
        seconds_cutoff = self.max_file_age * seconds_per_day

        pruned = set()

        def get_next_to_remove(files) -> int:
            if not files:
                return

            # Remove really old files first, if beyond the cutoff:
            max_age = max(files)
            if max_age > seconds_cutoff:
                return max_age

            # Remove files from earlier today:
            today_files = {delta: fn for delta, fn in files.items()
                           if delta < seconds_per_day}
            if len(today_files) > self.max_files_per_day:
                return max(today_files)

        while True:
            age = get_next_to_remove(files)
            if age is None:
                break

            fn = files.pop(age)
            self.files.pop(fn)

            self.log.info('Removing file %s (%s days old)',
                          fn, age / seconds_per_day)
            try:
                fn.unlink()
            except Exception:
                self.log.exception('Failed to remove %s', fn)
            else:
                self.log.info('Removed %s', fn)

            pruned.add(fn)

        return pruned

    def rotate_in_file(self, fn: pathlib.Path) -> set:
        """
        Move a valid file from another location to `self.filename` and prune.

        Returns
        -------
        pruned : set
            The set of pruned files.
        """

        if self.filename.exists():
            now = datetime.datetime.now()
            rename_to = now.strftime(self._date_format)
            self.log.info('Renaming %s to %s', self.filename, rename_to)
            rename_to = pathlib.Path(self.filename.parent, rename_to)
            try:
                self.filename.rename(rename_to)
            except Exception:
                self.log.exception('Failed to rotate out file')
            else:
                self.files[rename_to] = now

        pathlib.Path(fn).rename(self.filename)
        return self.prune_files()


def _to_json_data(value):
    """Ensure any numpy values don't leak through."""
    if hasattr(value, 'tolist'):
        # This works for scalars (e.g., np.uint32(5).tolist() = int(5))
        # along with ndarrays)
        return value.tolist()
    return value


def get_autosave_fields(pvprop, channeldata):
    """Get all autosaved fields from a pvproperty."""
    for name in (pvprop.autosave.get('fields', None) or []):
        field = getattr(channeldata.field_inst, name, None)
        if field is not None:
            yield name, _to_json_data(field.value)


class AutosaveHelper(PVGroup):
    filename = 'autosave.json'
    period = 30

    autosave_hook = pvproperty(
        read_only=True,
        name=':__autosave_hook__',
        doc='Internal hook which handles autosave functionality',
    )

    def __init__(self, *args, file_manager: RotatingFileManager = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        if file_manager is None:
            file_manager = RotatingFileManager(self.filename)
        self.file_manager = file_manager
        self.filename = self.file_manager.filename

    @autosave_hook.startup
    async def autosave_hook(self, instance, async_lib):
        """
        A startup hook which lives until the IOC exits.

        Initially restores values from the autosave file `self.filename`, then
        periodically - at `self.period` seconds - saves autosave data to
        `self.filename`.
        """
        await self.restore_from_file(self.filename)
        while True:
            await async_lib.library.sleep(self.period)
            await self.save()

    def find_autosave_properties(self):
        """Yield (pvprop, channeldata) for all tagged with `autosaved`."""
        ioc = self.parent
        for dotted_attr, pvprop in ioc._pvs_.items():
            if hasattr(pvprop, 'autosave'):
                channeldata = operator.attrgetter(dotted_attr)(ioc)
                yield pvprop, channeldata

    def prepare_data(self):
        """Generate the autosave dictionary."""
        return {
            channeldata.pvname: {
                'value': _to_json_data(channeldata.value),
                'fields': dict(get_autosave_fields(pvprop, channeldata))
            }
            for pvprop, channeldata in self.find_autosave_properties()
        }

    async def restore_from_file(self, filename):
        """Restore from the autosave file."""
        filename = pathlib.Path(filename)
        if not filename.exists():
            self.log.warning('Autosave file does not exist: %s', filename)
            return

        try:
            with open(filename, 'rt') as f:
                data = json.load(f)
        except Exception:
            self.log.exception('Failed to load JSON from %s', filename)
            return

        try:
            await self.restore_values(data)
        except Exception:
            self.log.exception('Failed to restore values from %s', filename)
            return

    async def restore_values(self, data):
        """Restore given the autosave file ``data`` dictionary."""
        for pvname, info in data.items():
            try:
                pvprop = self.parent.pvdb[pvname]
            except KeyError:
                self.log.error('Autosave pvname not in database: %s', pvname)
                continue

            try:
                await pvprop.write(info['value'])
            except Exception as ex:
                self.log.exception('Autosave restore failed: %s %s', pvname,
                                   ex)
            else:
                self.log.info('Restored %s => %s', pvname, pvprop.value)

            fields = info.get('fields', None) or {}
            for field_name, field_value in fields.items():
                try:
                    field = getattr(pvprop.field_inst, field_name)
                    await field.write(field_value)
                except Exception as ex:
                    self.log.exception(
                        'Autosave restore failed: %s field %s = %s %s', pvname,
                        field_name, field_value, ex)
                else:
                    self.log.info('Restored %s field %s => %s', pvname,
                                  field_name, field.value)

    async def save(self, data=None):
        """Save autosave ``data`` dictionary with the file manager."""
        try:
            if data is None:
                data = self.prepare_data()

            with tempfile.NamedTemporaryFile(mode='wt', delete=False,
                                             dir=self.file_manager.directory,
                                             ) as stream:
                json.dump(data, stream)
                filename = stream.name
        except Exception:
            self.log.exception('Failed to save the current state')
            return

        try:
            self.file_manager.rotate_in_file(pathlib.Path(filename))
        except Exception:
            self.log.exception('Rotating in save file failed')


def autosaved(pvprop, fields=None):
    """
    `pvproperty` wrapper which tags it as something that should be autosaved.

    Parameters
    ----------
    pvprop : pvproperty
        The pvproperty to wrap.

    fields : list, optional
        The list of fields to save, if using records.

    Returns
    -------
    pvproperty
        The pvproperty passed in.

    Examples
    --------

    ::
        value = autosaved(pvproperty(1.0))
    """

    if fields is None:
        fields = {'description'}

    pvprop.autosave = {'fields': fields}
    return pvprop
