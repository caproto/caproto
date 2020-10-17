*************************
IOC Template Cookiecutter
*************************

Caproto IOCs are easy to get started with and only require a single source code
file as shown in the many examples provided here.

For larger projecs, making a single caproto IOC into its own Python package
brings along some benefits:

1. Easily installed into a Python environment
2. Ability to add command-line hooks
3. Better structure - relatve imports
4. Add tests, documentation

To ease this process, caproto offers a "cookiecutter_" template.

The Cookiecutter
================

The cookiecutter_ is available in the caproto organization on GitHub.

Example
=======

The steps outlining an IOC creation are tersely shown here for a quick example.

.. code-block:: sh

  # Install cookiecutter
  $ pip install cookiecutter

  # Use the cookiecutter
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

  # Create a test environment
  $ conda create -n my_test_env python=3.7
  $ conda activate my_test_env

  # Install the project in that environment
  $ cd project_name
  $ pip install .

  # Run the IOC
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

  # Alternatively:
  $ python -m project_name --list-pvs

  # Build the docs:
  $ cd docs
  $ make html

  # Open them in your browser:
  # (macOS)
  $ open build/html/index.html
  # (Linux)
  $ xdg-open build/html/index.html


.. _cookiecutter: https://github.com/caproto/cookiecutter-caproto-ioc
