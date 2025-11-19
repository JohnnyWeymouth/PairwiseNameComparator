import sys
from setuptools import setup, Extension
from Cython.Build import cythonize

# Detect OS to set correct OpenMP flags
if sys.platform.startswith("win"):
    openmp_arg = '/openmp'
else:
    openmp_arg = '-fopenmp'

extensions = [
    Extension(
        "parallel_dict_lookup",
        ["parallel_dict_lookup.pyx"],
        extra_compile_args=[openmp_arg, '-O3'],
        extra_link_args=[openmp_arg],
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