import json
import logging
import logging.handlers
import pathlib

from . import PVGroup, PVSpec, pvproperty


def get_autosave_fields(pvprop):
    """Get all autosaved fields from a pvproperty."""
    for name in (pvprop.pvspec.autosave.get('fields', None) or []):
        field = getattr(pvprop.field_inst, name, None)
        if field is not None:
            yield name, field.value


class AutosaveHelper(PVGroup):
    filename = 'autosave.json'
    period = 30

    autosave_hook = pvproperty(read_only=True, name=':__autosave_hook__')

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

            handler = logging.handlers.RotatingFileHandler(
                self.filename,
                mode='wt',
                backupCount=5,
            )

            handler.stream.close()
            # TODO: only rotate after a day or something
            handler.doRollover()
            await self.save(handler.stream)
            handler.stream.flush()

    def find_autosave_properties(self):
        """Yield (pvname, pvprop) for all tagged with `autosaved`."""
        for pvname, pvprop in self.parent.pvdb.items():
            try:
                autosave = pvprop.pvspec.autosave
            except AttributeError:
                continue

            if autosave:
                yield pvname, pvprop

    def prepare_data(self):
        """Generate the autosave dictionary."""
        return {
            pvname: {'value': pvprop.value,
                     'fields': dict(get_autosave_fields(pvprop))
                     }
            for pvname, pvprop in self.find_autosave_properties()
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

    async def save(self, stream, data=None):
        """Save autosave ``data`` dictionary to the stream."""
        if data is None:
            data = self.prepare_data()

        json.dump(data, stream)


class AutosavedPVSpec(PVSpec):
    """A hack to enhance the inflexible PVSpec with autosave settings."""
    autosave = None

    def _replace(self, **kwargs):
        # NOTE: a further hack: this is a feature from `namedtuple` that's used
        # to replace item(s) in the tuple, returning a newly modified copy.
        # Here, we attach on `autosave` settings after performing the replace.
        replaced = super()._replace(**kwargs)
        replaced.autosave = self.autosave
        return replaced


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

    Example
    -------

    At the top-level PVGroup, ensure only one AutosaveHelper SubGroup has been
    added. Then, wrap any pvproperty to be saved with ``autosaved``:

    ::

        autosave_helper = SubGroup(AutosaveHelper)
        value = autosaved(pvproperty(1.0))
    """

    if fields is None:
        fields = {'description'}

    # A hack to enhance the inflexible PVSpec:
    pvspec = AutosavedPVSpec(**pvprop.pvspec._asdict())
    pvspec.autosave = {'fields': fields}
    pvprop.pvspec = pvspec
    return pvprop
