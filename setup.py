import os
import platform
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel

class BuildWithBinaries(build_py):
    """Custom build command to include Go binaries"""
    def run(self):
        # Run the standard build
        build_py.run(self)
        
        # Copy binaries to the build directory
        if not self.dry_run:
            binary_dir = Path("binaries")
            if binary_dir.exists():
                target_dir = Path(self.build_lib) / "src" / "bin"
                target_dir.mkdir(parents=True, exist_ok=True)
                
                for binary in binary_dir.glob("*"):
                    if binary.is_file():
                        self.copy_file(str(binary), str(target_dir / binary.name))
                        # Make binary executable on Unix
                        if binary.suffix != '.exe':
                            os.chmod(str(target_dir / binary.name), 0o755)

class BdistWheelPlatSpecific(bdist_wheel):
    """Custom wheel command to mark the wheel as platform-specific"""
    def finalize_options(self):
        bdist_wheel.finalize_options(self)
        # Mark as not pure Python since we include binaries
        self.root_is_pure = False

    def get_tag(self):
        # This will be overridden by --plat-name in the build command
        python, abi, plat = bdist_wheel.get_tag(self)
        # Use py3 for Python version, none for ABI (no C extensions)
        return 'py3', 'none', plat

def get_binary_name():
    """Determine which binary to use based on platform"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Normalize architecture names
    if machine in ('x86_64', 'amd64'):
        arch = 'amd64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64'
    else:
        arch = machine
    
    if system == 'windows':
        return f"PairwiseNameComparator.exe"
    else:
        return f"PairwiseNameComparator"

# Read version from a version file or set it directly
VERSION = "0.1.4"

# Read long description from README
long_description = ""
readme_path = Path("README.md")
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="pairwisenamecomparator",
    version=VERSION,
    description="An efficient Python package for all-to-all comparisons of large datasets of names",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/PairwiseNameComparator",
    packages=["src"],
    python_requires=">=3.8",
    install_requires=[
        "rich>=10.0.0",
        "Unidecode>=1.2.0",
        "fuzzywuzzy>=0.18.0",
        "python-Levenshtein>=0.25.1",
        "HungarianScorer==1.0.2",
        "RapidFuzz>=3.0.0",
    ],
    # Include the binaries directory in the package
    package_data={
        "src": ["bin/*"],
    },
    include_package_data=True,
    cmdclass={
        'build_py': BuildWithBinaries,
        'bdist_wheel': BdistWheelPlatSpecific,
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Go",
    ],
)