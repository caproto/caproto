***************
Install Caproto
***************

You can install caproto using pip or from source.

First verify that you have Python 3.6+.

.. code-block:: bash

   python3 --version

If necessary, install it by your method of choice (apt, Homebrew, conda, etc.).

Installation Using Pip
======================

.. code-block:: bash

   python3 -m pip install "caproto[complete]"

Minimal Installation Using Pip
==============================

The complete installation includes several optional dependences. For an
extremely lightweight installation, install caproto alone:

.. code-block:: bash

   python3 -m pip install caproto

Caproto's command-line, synchronous, and threading clients will work in this
mode, as will its asyncio server, because these rely only on built-in Python
modules. Caproto's trio and curio servers will not work unless trio and curio
are installed.

If numpy is not installed, caproto falls back on Python's built-in ``array``
module. This choice can be manually controlled via
``caproto.select_backend('numpy')`` and ``caproto.select_backend('array')``.

Other, intermediate combinations are also conveniently available:

.. code-block:: bash

   python3 -m pip install "caproto[standard]"  # includes numpy, netifaces
   python3 -m pip install "caproto[async]"  # includes the async libs

Installation from Source
========================

.. code-block:: bash

    git clone https://github.com/NSLS-II/caproto
    cd caproto
    pip install -e .

To install all the optional dependencies as well, use:

.. code-block:: bash

    pip install -e .[complete]
