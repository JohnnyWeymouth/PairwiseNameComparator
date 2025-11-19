import sys
import os
from setuptools import setup, Extension
from Cython.Build import cythonize

# 1. Standard OpenMP flags for Windows/Linux
if sys.platform.startswith("win"):
    compile_args = ['/openmp']
    link_args = []
elif sys.platform == 'darwin':
    # 2. macOS (Apple Clang) requires these specific flags
    compile_args = ['-Xpreprocessor', '-fopenmp']
    link_args = ['-lomp']
else:
    # 3. Linux (GCC)
    compile_args = ['-fopenmp']
    link_args = ['-fopenmp']

extensions = [
    Extension(
        "parallel_dict_lookup",
        ["parallel_dict_lookup.pyx"],
        extra_compile_args=compile_args + ['-O3'],
        extra_link_args=link_args,
    )
]

setup(
    name="parallel_dict_lookup",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'boundscheck': False,
            'wraparound': False,
        }
    ),
)