"""Include snippets/templates in installed wheels without duplicating source assets."""
from pathlib import Path
from shutil import copytree
from setuptools import setup
from setuptools.command.build_py import build_py

BASE=Path(__file__).resolve().parent

class BuildWithExamples(build_py):
    def run(self):
        super().run()
        destination=Path(self.build_lib)/"cfx_devkit"/"_assets"
        for name in ("templates","snippets"):
            copytree(BASE/name,destination/name,dirs_exist_ok=True)

setup(cmdclass={"build_py":BuildWithExamples})
