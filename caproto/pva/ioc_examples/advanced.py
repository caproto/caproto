#!/usr/bin/env python3
"""
An advanced caproto-pva server that does not rely on the PVAGroup magic.

This is **not** for the average user.
"""
import warnings

import caproto.pva as pva
from caproto.pva.server import ioc_arg_parser, run


@pva.pva_dataclass
class MyData:
    value: int
    info: str


@pva.pva_dataclass(name='epics:nt/NTScalar:1.0')
class NormativeIsh:
    value: float

    @pva.pva_dataclass
    class alarm_t:
        severity: pva.Int32
        status: pva.Int32
        message: str

    alarm: alarm_t

    @pva.pva_dataclass
    class time_t:
        secondsPastEpoch: pva.Int64
        nanoSeconds: pva.UInt32
        userTag: pva.UInt32

    timeStamp: time_t


pvdb = {
    'test': MyData(value=5, info='a string'),
    'test2': MyData(value=6, info='a different string'),
    'test3': NormativeIsh(value=1.0),
}


class BasicDataWrapper(pva.DataWrapperBase):
    """
    A basic wrapper for dataclasses to support caproto-pva's server API.

    Parameters
    ----------
    data : PvaStruct
        The dataclass holding the data.

    pvname : str
        The associated name of the data.
    """

    async def authorize(self,
                        operation: pva.AuthOperation, *,
                        authorization,
                        request=None):
        """
        Authenticate `operation`, given `authorization` information.

        In the event of successful authorization, a dataclass defining the data
        contained here must be returned.

        In the event of a failed authorization, `AuthenticationError` or
        similar should be raised.

        Returns
        -------
        data

        Raises
        ------
        AuthenticationError
        """
        # TODO: add functionality here
        if authorization['method'] == 'ca':
            # user = authorization['data'].user
            # if user != 'klauer':
            #     raise AuthenticationError(f'No, {user}.')
            ...
        elif authorization['method'] in {'anonymous', ''}:
            ...

        return self.data

    async def read(self, request):
        # TODO: add functionality here
        # print('Saw read', self.name, request)
        return await super().read(request)

    async def write(self, update: pva.DataWithBitSet):
        # TODO: add functionality here
        # print('Saw write', self.name, update)
        return await super().write(update)


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='caproto:pva:',
        desc='A basic caproto-pva test server.'
    )

    prefix = ioc_options['prefix']
    prefixed_pvdb = {
        prefix + key: BasicDataWrapper(name=prefix + key, data=value)
        for key, value in pvdb.items()
    }
    warnings.warn("The parsed IOC options are ignored by this IOC for now.")
    run(prefixed_pvdb, **run_options)


if __name__ == '__main__':
    main()
