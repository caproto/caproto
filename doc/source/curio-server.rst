.. currentmodule:: caproto.curio.server

*******************
Asynchronous Server
*******************

The :mod:`caproto.curio.server` implements a Channel Access server using the
curio framework for asynchronous programming in Python, making use of Python's
new async/await syntax. Curio is not a required dependeny of caproto; you may
need to install it separately using pip:

.. code-block:: bash

    pip install curio

Here is an example. We begin by defining a dictionary mapping channel names to
objects encapsulating a value and (optionally) associated metadata. We pass
this to a :class:`Context` object with a given address. Calling
:meth:`Context.run` creates a curio task that starts the server.

.. code-block:: python

    import curio
    from caproto.curio.server import Context, find_next_tcp_port
    from caproto import ChannelDouble, ChannelEnum, ChannelInteger

    pvdb = {'pi': ChannelDouble(value=3.14,
                                lower_disp_limit=3.13,
                                upper_disp_limit=3.15,
                                lower_alarm_limit=3.12,
                                upper_alarm_limit=3.16,
                                lower_warning_limit=3.11,
                                upper_warning_limit=3.17,
                                lower_ctrl_limit=3.10,
                                upper_ctrl_limit=3.18,
                                precision=5,
                                units='doodles',
                                ),
            'enum': ChannelEnum(value='b',
                                enum_strings=['a', 'b', 'c', 'd'],
                                ),
            'int': ChannelInteger(value=0,
                                  units='doodles',
                                  ),
            }

    ctx = Context('0.0.0.0', find_next_tcp_port(), pvdb)
    curio.run(ctx.run())
