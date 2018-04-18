#!/usr/bin/env python3
import re
import logging

import asks  # for http requests through curio

import urllib.request
import urllib.parse
from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.server import pvproperty, PVGroup


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
        m = re.search(r'<span class=bld>([^ ]*)',
                      resp.content.decode('latin-1'))
        return float(m.groups()[0])


if __name__ == '__main__':
    # usage: currency_conversion.py [PREFIX]
    import curio
    import sys

    try:
        prefix = sys.argv[1]
    except IndexError:
        prefix = 'currency_conversion:'

    set_logging_level(logging.DEBUG)
    asks.init('curio')
    ioc = CurrencyConversionIOC(prefix=prefix)
    print('PVs:', list(ioc.pvdb))
    curio.run(start_server, ioc.pvdb)
