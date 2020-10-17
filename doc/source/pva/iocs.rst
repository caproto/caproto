*******************************
Input-Output Controllers (IOCs)
*******************************

In this section, we will review some of the example IOCs that are included with
caproto, intended as demonstrations of what is possible.

.. note::

    Please note that this is preliminary API and may very likely change in
    future releases.

Type Annotations
================

Python type annotations are the primary method used to generate PVA-compatible
data structures for usage in an IOC.

This makes for reasonably compact and easy definitions of new types.  A simple
example may be:

.. code-block:: python

    from caproto import pva

    @pva.pva_dataclass
    class MyData:
        value: int
        info: str


This creates a data structure named ``MyData`` with two fields ``value``
(containing an integer - ``int64``) and ``info`` (containing a variable-length
string).

Arrays
------

Arrays can be specified using Python standard library annotations:

.. code-block:: python

    from typing import List

    from caproto import pva

    @pva.pva_dataclass
    class MyData:
        value_array: List[int]
        info: str


Specific Types
--------------

Using the Python built-in types implies usage of the maximum supported
compatible data type - that is, ``int`` implies a 64-bit signed integer,
``float`` implies a double (64-bit).

.. code-block:: python

    from typing import List

    from caproto import pva

    @pva.pva_dataclass
    class MyData:
        list_of_bytes: List[pva.UInt8]
        list_of_int32: List[pva.Int32]
        float_value: pva.Float32


Unions and Nested Types
-----------------------

Nesting data types is supported, inside or outside of the class body:

.. code-block:: python

    from caproto import pva

    @pva.pva_dataclass
    class NestedData:
        @pva.pva_dataclass
        class MyData:
            value: int
            info: str

        my_data: MyData
        value: float


Basic support for union types is also present:

.. code-block:: python

    from typing import Union

    from caproto import pva

    @pva.pva_dataclass
    class MyData:
        to_form_a: str
        more_perfect: Union[float, str]


Alternatively:

.. code-block:: python

    from typing import Union
    from caproto import pva


    @pva.pva_dataclass(union=True)
    class MyUnion:
        string_value: str
        float_value: float


    @pva.pva_dataclass
    class MyData:
        to_form_a: str
        more_perfect: MyUnion


The key for the above is that only one value may be non-``None`` for it to
be selected automatically.


Unsupported Types
-----------------

Some types are not yet supported, though they currently have annotations:

    * BoundedString
    * Float16
    * Float128


PVAGroup
========

.. note::

    While caproto-pva supports an "expert" (non-magical) method of writing
    IOCs, but these are considered advanced usage and are not documented here.
    An example of one may be found in the "advanced" example
    (:mod:`caproto.pva.ioc_examples.advanced`)


To define an IOC, we first define a new :class:`~caproto.pva.PVAGroup`
subclass.


.. code-block:: python

    import caproto.pva as pva

    class MyIOC(pva.PVAGroup):
        ...


There is no data contained in this just yet, so we need to add some
:class:`~caproto.pva.pvaproperty` attributes.  These act something like
Python's built-in `property` decorator.

The following IOC class, upon instantiation, will generate one PV named
``"value"`` - not including a prefix - which contains an ``NTScalar`` floating
point value:

.. code-block:: python

    import caproto.pva as pva

    class MyIOC(pva.PVAGroup):
        value = pva.pvaproperty(value=1.234)


Data type support is not just limited to normative types.  One may create their
own data type as described in _`Type Annotations`.

.. code-block:: python

    import caproto.pva as pva


    @pva.pva_dataclass
    class MyData:
        value: int
        info: str

    class MyIOC(pva.PVAGroup):
        value = pva.pvaproperty(value=MyData(value=1, info='testing'))


Adding a bit of boilerplate, any of the above IOCs can be run by simply
executing the given Python source code:


.. code-block:: python

    import caproto.pva as pva

    class MyIOC(pva.PVAGroup):
        value = pva.pvaproperty(value=1.234)


    def main():
        ioc_options, run_options = ioc_arg_parser(
            default_prefix='caproto:pva:',
            desc='A basic caproto-pva test server.'
        )

        ioc = MyIOC(**ioc_options)
        run(ioc.pvdb, **run_options)


    if __name__ == '__main__':
        main()


The :func:`~caproto.pva.ioc_arg_parser` handles parsing arguments, and
:func:`~caproto.pva.run` handles setting up the async library and booting the
IOC.


pvaproperty
-----------

Handling put
^^^^^^^^^^^^

.. code-block:: python

    import caproto.pva as pva

    class MyIOC(pva.PVAGroup):
        value = pva.pvaproperty(value=1.234)

        @value.putter
        async def value(self, instance, update: pva.WriteUpdate):
            """
            Put handler.

            Default handling: `update.accept()` (take everything)
            """


Key-based accepting and rejecting of values:

1. ``update.accept('value', 'info')``
2. ``update.reject('info')``
3.  Checking if a key is included in an update, and updating based on that:

    .. code-block:: python

        if 'value' in update:
            instance.value = update.instance.value


Handling RPC calls
^^^^^^^^^^^^^^^^^^


.. code-block:: python

    class MyIOC(PVAGroup):
        rpc = pvaproperty(value=MyData())

        @rpc.call
        async def rpc(self, instance, data):
            # It's likely but not required that normative type stuff comes
            # through ``data``.
            print('RPC call data is', data)
            print('Scheme:', data.scheme)
            print('Query:', data.query)
            print('Path:', data.path)

            # Echo back the query value, if available:
            query = data.query
            value = int(getattr(query, 'value', '1234'))
            return MyData(value=value)



Startup and shutdown methods
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When the server starts up, it can optionally call startup hooks for each
pvaproperty.

.. code-block:: python

    class MyIOC(PVAGroup):
        swap_a = pvaproperty(value=6)
        swap_b = pvaproperty(value=7)

        @swap_a.startup
        async def swap_a(self, instance, async_lib):
            while True:
                async with self.swap_a as a, self.swap_b as b:
                    # Swap values
                    a.value, b.value = b.value, a.value

                await async_lib.library.sleep(2.0)


``async_lib`` here is a shim that abstracts away the async library, whether
it be asyncio, curio, trio, or something else.

A shutdown hook has the same API and allows for resource cleanup prior to the
process exiting.


Handling Authentication
^^^^^^^^^^^^^^^^^^^^^^^

This isn't fully exposed yet in the pvaproperty API.


AsyncLibraryLayer
=================

Frequently referred to as ``async_lib`` in ``startup`` hooks, the
:class:`AsyncLibraryLayer` class is a shim that abstracts away the async
library, whether it be asyncio, curio, trio, or something else.

Attributes guaranteed to exist are:

1. ``name`` - the name of the asyncio library
2. ``library`` - the library module itself (e.g., ``asyncio``)
3. ``ThreadsafeQueue`` - a thread-safe queue with a common API

Additionally, one may assume the ``library.sleep`` coroutine exists.


Using the IOC Examples
======================

.. currentmodule:: caproto.pva.ioc_examples

They can be started like so:

.. code-block:: bash

    $ python -m caproto.pva.ioc_examples.normative
    [I 13:02:01.350       server:  127] Asyncio server starting up...
    [I 13:02:01.350       server:  128] Server GUID is: 0x313565616438386234356637
    [I 13:02:01.350       server:  143] Listening on 0.0.0.0:5075
    [I 13:02:01.351       server:  204] Server startup complete.

and stopped using Ctrl+C:

.. code-block:: bash

    ^C
    [I 13:02:19.129       server:  212] Server task cancelled. Will shut down.
    [I 13:02:19.129       server:  222] Server exiting....


Use ``--list-pvs`` to display which PVs they serve:

.. code-block:: bash

    $ python -m caproto.pva.ioc_examples.normative --list-pvs
    [I 13:02:33.318       server:  127] Asyncio server starting up...
    [I 13:02:33.318       server:  128] Server GUID is: 0x393063653765653064633235
    [I 13:02:33.318       server:  143] Listening on 0.0.0.0:5075
    [I 13:02:33.319       server:  204] Server startup complete.
    [I 13:02:33.319       server:  207] PVs available:
        caproto:pva:bool
        caproto:pva:int
        caproto:pva:float
        caproto:pva:str
        caproto:pva:int_array
        caproto:pva:float_array
        caproto:pva:string_array
        server

and use ``--prefix`` to conveniently customize the PV prefix.

Type ``python3 -m caproto.pva.ioc_examples.normative -h`` for more options.

``caproto-pva`` does not yet have an option for getting a PV list as the
built-in epics-base ``pvlist`` does, but the servers support the interface
required for this information.

.. code-block:: bash

    # NOTE: The following requires epics-base to be installed, for now.
    $ pvlist
    GUID 0x393063653765653064633235, version 1: tcp@[10.0.0.2:5075]

    $ pvlist 0x393063653765653064633235
    caproto:pva:bool
    caproto:pva:float
    caproto:pva:float_array
    caproto:pva:int
    caproto:pva:int_array
    caproto:pva:str
    caproto:pva:string_array


Examples
========

Normative Types
---------------

Normative types (``NTScalar``, ``NTScalarArray``) are data types that are
of a standardized form, containing data one might expect from Channel Access
V3 data types.  At minimum, these are guaranteed to contain a ``value`` field,
but may also include control, display, and alarm information with limits,
units, and descriptions.

caproto server normative values (by default) include all additional metadata.

.. autosummary::
    :toctree: generated

    normative
    normative.NormativeIOC


.. literalinclude:: ../../../caproto/pva/ioc_examples/normative.py

Groups
------

The full set of possibilities with what groups and properties can do.

.. autosummary::
    :toctree: generated

    group
    group.MyIOC


.. literalinclude:: ../../../caproto/pva/ioc_examples/group.py
