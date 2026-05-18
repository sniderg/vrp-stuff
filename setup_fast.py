from setuptools import setup
from Cython.Build import cythonize
import numpy

setup(
    name="inventory_fast",
    ext_modules=cythonize("roadef_tools/inventory_fast.pyx"),
    include_dirs=[numpy.get_include()],
    packages=[] # Don't try to discover packages
)
