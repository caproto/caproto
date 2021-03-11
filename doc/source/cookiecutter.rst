**************************
IOC Template Cookiecutters
**************************

Caproto IOCs are easy to get started with and only require a single source code
file as shown in the many examples provided here.

For larger projecs, making a single caproto IOC into its own Python package
brings along some benefits:

1. Easily installed into a Python environment
2. Ability to add command-line hooks
3. Better structure - relatve imports
4. Add tests, documentation

To ease this process, caproto offers two "cookiecutter_" templates, one for
generating your IOC package and one for creating a startup script that can
be used by procServ, systemd, init.d, and so on.

IOC Cookiecutter
================

The cookiecutter_ is available in the caproto organization on GitHub.

The steps outlining an IOC creation are tersely shown here for a quick example.

Install cookiecutter
^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  $ pip install cookiecutter

Use the cookiecutter
^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  $ cookiecutter https://github.com/caproto/cookiecutter-caproto-ioc
  project_name [project_name]:
  github_repo_group [pcdshub]:
  repo_name [project_name]:
  default_prefix [SIM:]:
  author_name [SLAC National Accelerator Laboratory]:
  email []:
  folder_name [project_name]:
  import_name [project_name]:
  description [project_name]:
  Select license:
  1 - SLAC
  2 - BNL
  3 - MIT
  4 - BSD-3
  Choose from 1, 2, 3, 4 [1]:
  Select auto_git_setup:
  1 - no
  2 - yes
  Choose from 1, 2 [1]:
  git_remote_name [origin]:
  Select auto_doctr_setup:
  1 - no
  2 - yes
  Choose from 1, 2 [1]:
  Select use_x11_on_travis:
  1 - no
  2 - yes
  Choose from 1, 2 [1]:
  year [2020]:


Create a test environment
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  $ conda create -n my_test_env python=3.7
  $ conda activate my_test_env

Install the project in that environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  $ cd project_name
  $ pip install .

Run the IOC
^^^^^^^^^^^

.. code-block:: sh

  $ project_name --list-pvs
  [I 17:33:28.970       server:  133] Asyncio server starting up...
  [I 17:33:28.971       server:  146] Listening on 0.0.0.0:5064
  [I 17:33:28.972       server:  205] Server startup complete.
  [I 17:33:28.973       server:  207] PVs available:
      SIM:SampleValue
      SIM:SampleScanned
  This happens at IOC boot!
  Initial value was: 0.0
  Now it is: 0.1

  ^C
  [I 17:33:30.442       server:  212] Server task cancelled. Will shut down.
  [I 17:33:30.442       server:  222] Server exiting....

Alternatively:
^^^^^^^^^^^^^^

.. code-block:: sh

  $ python -m project_name --list-pvs

Build the docs:
^^^^^^^^^^^^^^^

.. code-block:: sh

  $ cd docs
  $ make html

Open them in your browser:
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  # (macOS)
  $ open build/html/index.html
  # (Linux)
  $ xdg-open build/html/index.html


Startup Script Cookiecutter
===========================

The startup_cookiecutter_ is available in the caproto organization on GitHub.

Before using this cookiecutter, you should already have a caproto-based IOC you
wish to create startup scripts for. Please consider starting with the
cookiecutter from the previous section.

With standard EPICS IOCs, the IOC supporting code tends to be reused many
times, with only a per-IOC startup script configuring which records get created
with what PV prefixes, device IP addresses, and so on.

This cookiecutter aims to do something similar - take your existing IOC source
code and easily template multiple instances of that IOC. Several key points
(and benefits in the author's opinion) of this method are:

1. Decoupling PVGroup source code from per-IOC settings.
2. A git submodule of the IOC source to specify a released (or unreleased)
   versino of the IOC source code.
3. An independent conda environment per IOC.

If you want to use your IOC with **procServ**, this is the cookiecutter for
you.

The steps outlining an IOC startup script creation are tersely shown here for a
quick example.

Install cookiecutter
^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

  $ pip install cookiecutter


Use the cookiecutter
^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

    $ cookiecutter https://github.com/pcdshub/cookiecutter-caproto-ioc-startup
    $ cd ioc-my-iocname

Customize any settings
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: sh

    $ vim config.sh

Run the IOC
^^^^^^^^^^^

.. code-block:: sh

    $ ./st.cmd
    [I 17:33:28.970       server:  133] Asyncio server starting up...
    [I 17:33:28.971       server:  146] Listening on 0.0.0.0:5064
    [I 17:33:28.972       server:  205] Server startup complete.
    [I 17:33:28.973       server:  207] PVs available:
        SIM:SampleValue
        SIM:SampleScanned
    This happens at IOC boot!
    Initial value was: 0.0
    Now it is: 0.1

    ^C
    [I 17:33:30.442       server:  212] Server task cancelled. Will shut down.
    [I 17:33:30.442       server:  222] Server exiting....


.. _cookiecutter: https://github.com/caproto/cookiecutter-caproto-ioc
.. _startup_cookiecutter: https://github.com/caproto/cookiecutter-caproto-ioc-startup
