#!/usr/bin/env python3
import re
import warnings

import asks
import urllib.request
import urllib.parse
from caproto.server import pvproperty, PVGroup, ioc_arg_parser, run


async def convert_currency(amount, from_currency, to_currency):
    'Perform the currency conversion'
    params = urllib.parse.urlencode({'a': amount,
                                     'from': from_currency,
                                     'to': to_currency,
                                     })
    resp = await asks.get('https://finance.google.com/finance/'
                          'converter?' + params)
    if resp.status_code != 200:
        warnings.warn(f"Request to Google return response status "
                      f"{resp.status_code} {resp.reason_phrase}. "
                      f"Setting value 'converted' PV to -1.")
        converted = -1
    else:
        m = re.search(r'<span class=bld>([^ ]*)',
                      resp.content.decode('latin-1'))
        converted = float(m.groups()[0])
    print(f'Converted {amount} {from_currency} to {to_currency} = {converted}')
    return converted


class CurrencyPollingIOC(PVGroup):
    from_currency = pvproperty(value=['BTC'])
    to_currency = pvproperty(value=['USD'])
    amount = pvproperty(value=[1])

    update_rate = pvproperty(value=[3.0])
    converted = pvproperty(value=[0.0])

    @converted.startup
    async def converted(self, instance, async_lib):
        'Periodically update the value'
        while True:
            # perform the conversion
            converted_amount = await convert_currency(
                amount=self.amount.value[0],
                from_currency=self.from_currency.value[0],
                to_currency=self.to_currency.value[0],
            )

            # update the ChannelData instance and notify any subscribers
            await instance.write(value=[converted_amount])

            # Let the async library wait for the next iteration
            await async_lib.library.sleep(self.update_rate.value[0])


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='currency_poll:',
        desc='Run an IOC with a periodically updating currency conversion.',
        supported_async_libs=('curio',))

    # Initialize this async HTTP library.
    asks.init('curio')

    ioc = CurrencyPollingIOC(**ioc_options)
    run(ioc.pvdb, **run_options)
