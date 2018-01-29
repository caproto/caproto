from distutils.core import setup
import glob
import setuptools
import versioneer


setup(name='caproto',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      author='Daniel Allan',
      description='a sans-I/O implementation of the EPICS Channel Access '
                  'protocol',
      packages=['caproto',
                'caproto.asyncio',
                'caproto.benchmarking',
                'caproto.curio',
                'caproto.examples',
                'caproto.ioc_examples',
                'caproto.sync',
                'caproto.tests',
                'caproto.threading',
               ],
      scripts=glob.glob('scripts/*'),
      )
