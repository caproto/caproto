import sys
from distutils.core import setup
from os import path

import setuptools  # noqa F401

import versioneer

# NOTE: This file must remain Python 2 compatible for the foreseeable future,
# to ensure that we error out properly for people with outdated setuptools
# and/or pip.
if sys.version_info < (3, 6):
    error = """
Caproto does not support Python 2.x, 3.0, 3.1, 3.2, 3.3, 3.4, or 3.5.
Python 3.6 and above is required. Check your Python version like so:

python --version

This may be due to an out-of-date pip. Make sure you have pip >= 9.0.1.
Upgrade pip like so:

pip install --upgrade pip
"""
    sys.exit(error)


classifiers = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.6',
    'Topic :: Scientific/Engineering :: Visualization',
    'License :: OSI Approved :: BSD License'
]

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'requirements-test.txt')) as requirements_file:
    test_requirements = [
        line for line in requirements_file.read().splitlines()
        if not line.startswith('#') and not line.startswith('git+')
    ]

extras_require = {
    'standard': ['netifaces', 'numpy', 'dpkt'],
    'async': ['curio>=1.2', 'trio>=0.12.1'],
}

extras_require['complete'] = sorted(set(sum(extras_require.values(), [])))
extras_require['test'] = sorted(set(sum(extras_require.values(), test_requirements)))

setup(name='caproto',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      author='Caproto Contributors',
      description='a sans-I/O implementation of the EPICS Channel Access '
                  'protocol',
      packages=setuptools.find_packages(where='.', exclude=['doc', '.ci']),
      entry_points={
          'console_scripts': [
              'caproto-get = caproto.commandline.get:main',
              'caproto-put = caproto.commandline.put:main',
              'caproto-monitor = caproto.commandline.monitor:main',
              'caproto-repeater = caproto.commandline.repeater:main',
              'caproto-shark = caproto.commandline.shark:main',
              'caproto-defaultdict-server = caproto.ioc_examples.pathological.defaultdict_server:main',
              'caproto-spoof-beamline = caproto.ioc_examples.pathological.spoof_beamline:main',
          ],
      },
      include_package_data=True,
      package_data={
          # NOTE: this is required in addition to MANIFEST.in, as that only
          # applies to source distributions

          # Include our documentation helpers and templates necessary to
          # rebuild record fields:
          '': ['*.rst', '*.jinja2'],
      },
      python_requires='>=3.6',
      classifiers=classifiers,
      extras_require=extras_require
      )
