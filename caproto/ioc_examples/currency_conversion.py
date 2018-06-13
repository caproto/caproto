#!/usr/bin/env python3
import re
import asks
import warnings

import urllib.request
import urllib.parse
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


class CurrencyConversionIOC(PVGroup):
    from_currency = pvproperty(value=['BTC'])
    to_currency = pvproperty(value=['USD'])
    amount = pvproperty(value=[1])

    @property
    def request_params(self):
        return urllib.parse.urlencode(
            {'a': self.amount.value[0],
             'from': self.from_currency.value[0],
             'to': self.to_currency.value[0],
             })

    @pvproperty(value=[0.0])
    async def converted(self, instance):
        resp = await asks.get('https://finance.google.com/finance/'
                              'converter?' + self.request_params)
        if resp.status_code != 200:
            warnings.warn(f"Request to Google return response status "
                          f"{resp.status_code} {resp.reason_phrase}. "
                          f"Setting value 'converted' PV to -1.")
            return -1
        else:
            m = re.search(r'<span class=bld>([^ ]*)',
                          resp.content.decode('latin-1'))
            return float(m.groups()[0])


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='currency:',
        desc='Run an IOC that performs a currency conversion when read.',
        supported_async_libs=('curio',))

    if run_options['module_name'] != 'caproto.curio.server':
        raise ValueError("This example must be run with '--async-lib curio'.")
    # Initialize this async HTTP library.
    asks.init('curio')

    ioc = CurrencyConversionIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
