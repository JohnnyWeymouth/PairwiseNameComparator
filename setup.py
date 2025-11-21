import os
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel

class BuildWithBinaries(build_py):
    def run(self):
        build_py.run(self)
        if not self.dry_run:
            binary_dir = Path("binaries")
            # We use self.get_package_dir to find where setuptools put the package
            # This avoids hardcoding "pairwisenamecomparator" if the detection varies
            pkg_name = self.distribution.packages[0]
            target_dir = Path(self.build_lib) / pkg_name / "bin"
            
            if binary_dir.exists():
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
    # This is the fix: Auto-detect the package folder
    packages=find_packages(),
    include_package_data=True,
    # Dynamically target the bin folder for whatever package was found
    package_data={
        "": ["bin/*"],
    },
    cmdclass={
        'build_py': BuildWithBinaries,
        'bdist_wheel': BdistWheelPlatSpecific,
    },
)