.. currentmodule:: caproto.threading.client

*****************************************
Thread-based Client Mirroring pyepics API
*****************************************

The :mod:`caproto.threading.client` implements a Channel Access client using
threads. It provides an interface familiar to pyepics users.

Before using you should start a CA repeater process in the background if one is
not already running. You may use the one from epics-base or one provided with
caproto as a CLI.

.. code-block:: bash

    caproto-reapeater &

.. code-block:: python

    from caproto.threading.client import caget, caput, get_pv

    # Simple functions
    caget('pvname')
    caput('pvname', 3)

    # Object-oriented interface
    pv = get_pv('pvname')
    pv.wait_for_connection()
    pv.get()
    pv.put(3)
