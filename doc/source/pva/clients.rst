Synchronous Client
==================


Accessing from the Command-line
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Get a PV:

.. code-block:: bash

    python3 -m caproto.pva.commandline.get caproto:pva:int


Set a PV:

.. code-block:: bash

    python3 -m caproto.pva.commandline.put caproto:pva:int 42


Monitor a PV:

.. code-block:: bash

    python3 -m caproto.pva.commandline.monitor caproto:pva:int
