=======
Servers
=======

.. note::

    If your goal is to write IOCs, see :doc:`iocs`.

Caproto includes three implementations of a Channel Access server for three
different Python concurrency libraries:

* asyncio (built in to Python, as part of its standard library)
* curio
* trio

To learn more about concurrency in Python (and in general) we recommend these
introductory resources, suggested by a caproto user:

* `Speed up your Python program with concurrency <https://realpython.com/python-concurrency/>`_
* `Async IO in Python: A Complete Walkthrough <https://realpython.com/async-io-python/>`_


Core API
--------

The core IOC code abstracts out the particular server implementation, so IOC
authors do not need to interact with the server API directly. The core server
API remains a work-in-progress and is subject to change, though as of 2021
it is likely mostly stable.

See more details in :doc:`server_api`.

Writing your own IOCs
---------------------

There is an entire chapter in this documentation dedicated to EPICS IOCs and
the related tools we have.  Take a look at :doc:`iocs` for more information.


Running multiple servers on one host
------------------------------------

For service discovery EPICS primarily relies on UDP broadcast (rsrv
also supports multicast, this is not (yet) supported by caproto).  To
achieve this all of the servers processes on a host bind the canonical
port (default 5064) with the ``SO_REUSEADDR`` and ``SO_REUSEPORT``
settings.  These settings allow multiple sockets (across different
processes or threads) to bind the same interface and port, `see this
SO post
<https://stackoverflow.com/questions/14388706/how-do-so-reuseaddr-and-so-reuseport-differ>`_
for more details.  When configured this way the UDP sockets:

* load balance between IOC processes for uni-cast messages (the exact
  method of load balancing changed with the 3.9 Linux kernel)
* sent to all IOC processes for broadcast messages

Because you `can not broadcast to 127.0.0.1
<https://www.mail-archive.com/freebsd-net@freebsd.org/msg07814.html>`__
if you bind your IOCs to the localhost interface you will be able to
talk to at most 1 of them from any given client.

If you want to put non-broadcast IPs in ``EPICS_CA_ADDR_LIST`` then
you can not run more than one IOC per host (because search requests will
be load balanced).

If you have a host with more than one interface and you want to bind
your IOCs to a specific interface doing so by specifying the broadcast
address will work, however in that case any uni-cast searches (ex a
specific IP in tho ``EPICS_CA_ADDR_LIST`` will be ignored).  Binding
to the specific interface using the ip adderesss will result in the
messages to the broadcast address being ignored and uni-cast messages
being load-balanced.

The EPICS wiki `has some additional details about how to set up
iptables
<https://wiki-ext.aps.anl.gov/epics/index.php/How_to_Make_Channel_Access_Reach_Multiple_Soft_IOCs_on_a_Linux_Host>`__
to work around this issue.
