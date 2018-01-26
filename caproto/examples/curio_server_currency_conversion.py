import re
import logging

import curio
import asks  # for http requests through curio

import urllib.request
import urllib.parse
from caproto.benchmarking import set_logging_level
from caproto.curio.server import start_server
from caproto.curio.high_level_server import pvproperty, PVGroupBase


class CurrencyConversionIOC(PVGroupBase):
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


def main(prefix, macros):
    set_logging_level(logging.DEBUG)
    asks.init('curio')
    ioc = CurrencyConversionIOC(prefix=prefix, macros=macros)
    curio.run(start_server, ioc.pvdb)


if __name__ == '__main__':
    main(prefix='currency:', macros={})
