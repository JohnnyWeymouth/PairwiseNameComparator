import os
from setuptools import setup, Extension
from Cython.Build import cythonize

# Read flags from the environment (set by cibuildwheel)
# If they aren't set, default to empty list
extra_compile_args = os.environ.get('CFLAGS', '').split()
extra_link_args = os.environ.get('LDFLAGS', '').split()

# Add optimization flag by default
extra_compile_args.append('-O3')

extensions = [
    Extension(
        "parallel_dict_lookup",
        ["parallel_dict_lookup.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
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