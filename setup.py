from distutils.core import setup
import glob
import setuptools  # noqa F401
import versioneer


classifiers = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.6',
    'Topic :: Scientific/Engineering :: Visualization',
    'License :: OSI Approved :: BSD License'
]

setup(name='caproto',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      author='Daniel Allan',
      description='a sans-I/O implementation of the EPICS Channel Access '
                  'protocol',
      packages=['caproto',
                'caproto.benchmarking',
                'caproto.curio',
                'caproto.examples',
                'caproto.ioc_examples',
                'caproto.server',
                'caproto.sync',
                'caproto.tests',
                'caproto.threading',
                'caproto.trio',
                ],
      scripts=glob.glob('scripts/*'),
      python_requires='>=3.6',
      classifiers=classifiers
      )
