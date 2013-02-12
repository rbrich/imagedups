#!/usr/bin/env python

from distutils.core import setup
from Cython.Build import cythonize
import os, shutil

# install imagedups without .py extension
shutil.copyfile('imagedups.py', 'build/imagedups')

setup(
    name='imagedups',
    version='0.0.1',
    description='Find duplicate images',
    author='Radek Brich',
    author_email='radek.brich@devl.cz',
    url='http://hg.devl.cz/imagedups/',
    keywords=['duplicate images', 'perceptual hash', 'pHash'],
    ext_modules = cythonize("phash.pyx"),
    packages=['imagedups'],
    scripts=['build/imagedups'],
    )

os.unlink('build/imagedups')
