#!/usr/bin/env python

import sys

from distutils.core import setup



readme = file('docs/README.txt','rb').read()

classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GPLv3',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering :: GIS',
]

 
extra = { }
if "--debian" in sys.argv:
   extra['data_files']=[('/etc', ['kmlmapserver.cfg'])]
   sys.argv.remove("--debian")
else:
   extra['data_files']=[('KmlMapServer', ['kmlmapserver.cfg'])]
    
setup(name='KmlMapServer',
      version='0.2',
      description='A KML publication service for MapServer layers',
      author='Guillaume Sueur - Neogeo Technologies',
      author_email='guillaume.sueur@neogeo-online.net',
      url='http://www.webmapping.fr/projects/kmlmapserver',
      long_description=readme,
      packages=['KmlMapServer'],
      package_data = {
        'KmlMapServer': ['Templates/*.xml'],
        },
      requires = ['mako','psycopg2'],
      #test_suite = 'tests.run_doc_tests',
      license="GPLv3",
      classifiers=classifiers, 
      **extra 
     )
