"""py2app build script for MacPhotoMaster.

Fast dev build (symlinks into this repo's venv, rebuilds instantly, not for
distribution — the source venv must stay in place for it to run):
    uv run python setup.py py2app -A

Standalone build (bundles everything, safe to move/copy or drag to Dock):
    uv run python setup.py py2app

Either produces dist/MacPhotoMaster.app.
"""

from pathlib import Path

from setuptools import setup
from py2app.build_app import py2app as py2app_command

APP = ["main.py"]

ICON_PATH = Path("resources/AppIcon.icns")

OPTIONS = {
    "argv_emulation": False,
    "packages": ["phototags"],
    "plist": {
        "CFBundleName": "MacPhotoMaster",
        "CFBundleDisplayName": "MacPhotoMaster",
        "CFBundleIdentifier": "photos.briansmith.macphotomaster",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
}
if ICON_PATH.exists():
    OPTIONS["iconfile"] = str(ICON_PATH)


class Py2AppIgnoringDependencies(py2app_command):
    """py2app refuses to build if install_requires is set, but setuptools
    auto-populates it from pyproject.toml's [project.dependencies]. Clear it
    here since a frozen app bundle doesn't need pip-style deps anyway."""

    def finalize_options(self) -> None:
        self.distribution.install_requires = None
        super().finalize_options()


setup(
    app=APP,
    options={"py2app": OPTIONS},
    cmdclass={"py2app": Py2AppIgnoringDependencies},
)
