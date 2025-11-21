import os
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel

class BuildWithBinaries(build_py):
    """Custom build command to include Go binaries"""
    def run(self):
        build_py.run(self)
        if not self.dry_run:
            binary_dir = Path("binaries")
            if binary_dir.exists():
                # Note: This path must match your new directory structure
                target_dir = Path(self.build_lib) / "pairwisenamecomparator" / "bin"
                target_dir.mkdir(parents=True, exist_ok=True)
                for binary in binary_dir.glob("*"):
                    if binary.is_file():
                        self.copy_file(str(binary), str(target_dir / binary.name))
                        if binary.suffix != '.exe':
                            os.chmod(str(target_dir / binary.name), 0o755)

class BdistWheelPlatSpecific(bdist_wheel):
    def finalize_options(self):
        bdist_wheel.finalize_options(self)
        self.root_is_pure = False

    def get_tag(self):
        python, abi, plat = bdist_wheel.get_tag(self)
        return 'py3', 'none', plat

setup(
    # We use find_packages() to automatically locate the new directory
    packages=find_packages(),
    include_package_data=True,
    # We keep package_data to ensure the bin folder is recognized as package data
    package_data={
        "pairwisenamecomparator": ["bin/*"],
    },
    cmdclass={
        'build_py': BuildWithBinaries,
        'bdist_wheel': BdistWheelPlatSpecific,
    },
)