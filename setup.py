#!/usr/bin/env python3

from distutils.core import setup
from Cython.Build import cythonize

setup(
    name='imagedups',
    version='0.0.1',
    description='Find duplicate images',
    author='Radek Brich',
    author_email='radek.brich@devl.cz',
    url='http://hg.devl.cz/imagedups/',
    keywords=['duplicate images', 'perceptual hash', 'pHash'],
    ext_modules = cythonize('pyx/phash.pyx'),
    packages=['imagedups'],
    scripts=['imagedups.py'],
    )

