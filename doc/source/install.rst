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

   python3 -m pip install -U "caproto[complete]"

Minimal Installation Using Pip
==============================

The complete installation includes several optional dependences. For an
extremely lightweight installation, install caproto alone:

.. code-block:: bash

   python3 -m pip install -U caproto

Caproto's command-line, synchronous, and threading clients will work in this
mode, as will its asyncio server, because these rely only on built-in Python
modules. Caproto's trio and curio servers will not work unless trio and curio
are installed.

If numpy is not installed, caproto falls back on Python's built-in ``array``
module. This choice can be manually controlled via
``caproto.select_backend('numpy')`` and ``caproto.select_backend('array')``.

Other, intermediate combinations are also conveniently available:

.. code-block:: bash

   python3 -m pip install -U "caproto[standard]"  # includes numpy, netifaces
   python3 -m pip install -U "caproto[async]"  # includes the async libs

Development Installation
========================

.. code-block:: bash

    git clone https://github.com/caproto/caproto
    cd caproto
    pip install -e .

To install all the optional dependencies as well, use:

.. code-block:: bash

    pip install -e .[complete]

Development
===========

For development, you will also want the dependencies for running the tests and
building the documentation:

.. code-block:: bash

    pip install -Ur requirements-test.txt
    pip install -Ur requirements-doc.txt

You may also want to use `pre-commit <https://pre-commit.com/>`_. This is
optional. It streamlines compliance with code style requirements. If you are a
first-time contributor or unfamiliar with "precommit" tools, feel free to
ignore.

.. code-block:: bash

   pip install pre-commit
   pre-commit install

This uses git hooks to check the changed files every time code is committed.

.. code-block:: bash

   echo "blah" >> setup.py
   git commit -am "test"   # fails due to linting

Use the git option ``--no-verify`` or ``-n`` to skip the checks.

.. code-block:: bash

   git commit -nam "test"  # commits anyway

You can run the checks manually on all files.

.. code-block:: bash

   # run on all files
   pre-commit run --all-files

To run the tests:

.. code-block:: bash

    python run_tests.py

Any argument will be passed through to ``pytest``. These are arguments are
commonly useful:

* ``-v`` verbose
* ``-s`` Do not capture stdout/err per test.
* ``-k EXPRESSION`` Filter tests by pattern-matching test name.

Many of the tests test caproto against EPICS' reference implementation. They
expect ``caget``, ``caput``, and ``softIoc`` executables to be available and
for ``EPICS_BASE`` to be set.

A small number of the tests test caproto against ``motorsim``. To skip these
tests, set the environment variable ``CAPROTO_SKIP_MOTORSIM_TESTS=1``.

To build the documentation:

.. code-block:: bash

    make -C doc html

Installation on iOS
===================

`Pythonista <http://omz-software.com/pythonista/>`_ brings support for Python
3.6 to iOS, meaning that you can run caproto rather easily right from your
iPhone or iPad.

To get started on iOS:

1. Purchase and install Pythonista from the app store.
2. Install `StaSh <https://github.com/ywangd/stash>`_ in Pythonista by creating
   a new script and running:

.. code-block:: python

   import requests as r; exec(r.get('https://bit.ly/get-stash').text)

3. Restart Pythonista and launch a StaSh shell. Install caproto with pip:

.. code-block:: bash

   $ pip install caproto

4. Open an example IOC and give it a try. To find the caproto examples, navigate to
   "Python Modules > site-packages-3 > caproto > ioc_examples > simple.py"

5. Tap the play button to run it.  From another computer on the same WiFi
   network, you should then be able to access the PVs served directly from your
   iOS device:

.. code-block:: bash

    $ caproto-get simple:A
    simple:A                   [1]

6. Some example IOCs are available in a separate repository, including access to the
   accelerometer, GPS, and text-to-speech engine. See
   `klauer/caproto_ios <https://github.com/klauer/caproto_ios>`_ for more
   information.
