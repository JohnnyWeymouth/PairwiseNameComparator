import sys
from setuptools import setup, Extension
from Cython.Build import cythonize

# Default flags
compile_args = []
link_args = []

# 1. Microsoft Visual C++ (Windows)
if sys.platform.startswith("win"):
    compile_args = ['/openmp']
    # No link args needed for MSVC usually

# 2. Apple Clang (macOS)
elif sys.platform == 'darwin':
    # These MUST be in this specific order
    compile_args = ['-Xpreprocessor', '-fopenmp']
    # Link against the OpenMP library
    link_args = ['-lomp']

# 3. GCC/Linux
else:
    compile_args = ['-fopenmp']
    link_args = ['-fopenmp']

# Always add optimization
compile_args.append('-O3')

extensions = [
    Extension(
        "parallel_dict_lookup",
        ["parallel_dict_lookup.pyx"],
        extra_compile_args=compile_args,
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