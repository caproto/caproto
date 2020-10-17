************
PVAccess API
************


.. currentmodule:: caproto.pva


Circuits
========

.. currentmodule:: caproto.pva._circuit

.. autoclass:: VirtualCircuit
    :members:

.. autoclass:: ClientVirtualCircuit
    :members:

.. autoclass:: ServerVirtualCircuit
    :members:


Server
======

.. currentmodule:: caproto.pva.server.common

.. autoclass:: ServerStatus
.. autoclass:: AuthOperation
.. autoclass:: SubscriptionSpec
.. autoclass:: Subscription
.. autoclass:: VirtualCircuit
    :members:

.. autoclass:: Context
    :members:


.. autoclass:: DataWrapperBase
    :members:


Command-line
------------

.. currentmodule:: caproto.pva.server.commandline

.. autofunction:: ioc_arg_parser
.. autofunction:: template_arg_parser
.. autofunction:: run


Magic
-----

.. currentmodule:: caproto.pva.server.magic

.. autoclass:: AuthenticationError
.. autoclass:: DatabaseDefinitionError

.. autoclass:: DataclassOverlayInstance
    :members:

.. autoclass:: WriteUpdate
    :members:

.. autoclass:: GroupDataWrapper
    :members:

.. autoclass:: pvaproperty
    :members:

.. autoclass:: PVAGroupMeta
    :members:

.. autoclass:: PVAGroup
    :members:

.. autoclass:: ServerRPC
    :members:

.. autofunction:: verify_getter
.. autofunction:: verify_putter
.. autofunction:: verify_rpc_call
.. autofunction:: verify_startup
.. autofunction:: verify_shutdown

Asyncio
-------

.. currentmodule:: caproto.pva.asyncio.server

.. autoclass:: VirtualCircuit
    :members:

.. autoclass:: Context
    :members:

.. autofunction:: start_server
.. autofunction:: run


Clients
=======

Synchronous
-----------

.. currentmodule:: caproto.pva.sync.client

.. autofunction:: read
.. autofunction:: monitor
.. autofunction:: read_write_read


Messages
========


.. currentmodule:: caproto.pva._messages

.. autoclass:: MessageHeader
    :members:

.. autofunction:: bytes_needed_for_command

.. autofunction:: header_from_wire

.. autofunction:: read_datagram

.. autofunction:: read_from_bytestream

Control
-------

.. autoclass:: BeaconMessage
    :members:

.. autoclass:: MessageHeaderLE
    :members:

.. autoclass:: MessageHeaderBE
    :members:

.. autoclass:: SetMarker
    :members:

.. autoclass:: AcknowledgeMarker
    :members:

.. autoclass:: SetByteOrder
    :members:

.. autoclass:: EchoRequest
    :members:

.. autoclass:: EchoResponse
    :members:


Application
-----------

.. autoclass:: ConnectionValidationRequest
    :members:

.. autoclass:: ConnectionValidationResponse
    :members:

.. autoclass:: Echo
    :members:

.. autoclass:: ConnectionValidatedResponse
    :members:

.. autoclass:: SearchRequest
    :members:

.. autoclass:: SearchResponse
    :members:

.. autoclass:: CreateChannelRequest
    :members:

.. autoclass:: CreateChannelResponse
    :members:

.. autoclass:: ChannelDestroyRequest
    :members:

.. autoclass:: ChannelDestroyResponse
    :members:

.. autoclass:: ChannelGetRequest
    :members:

.. autoclass:: ChannelGetResponse
    :members:

.. autoclass:: ChannelFieldInfoRequest
    :members:

.. autoclass:: ChannelFieldInfoResponse
    :members:

.. autoclass:: ChannelPutRequest
    :members:

.. autoclass:: ChannelPutResponse
    :members:

.. autoclass:: ChannelPutGetRequest
    :members:

.. autoclass:: ChannelPutGetResponse
    :members:

.. autoclass:: ChannelArrayRequest
    :members:

.. autoclass:: ChannelArrayResponse
    :members:

.. autoclass:: ChannelRequestDestroy
    :members:

.. autoclass:: ChannelRequestCancel
    :members:

.. autoclass:: ChannelMonitorRequest
    :members:

.. autoclass:: ChannelMonitorResponse
    :members:

.. autoclass:: ChannelProcessRequest
    :members:

.. autoclass:: ChannelProcessResponse
    :members:

.. autoclass:: ChannelRpcRequest
    :members:

.. autoclass:: ChannelRpcResponse
    :members:
