"""Collect license files from installed Python distributions for the preview."""

import shutil
from importlib import metadata
from pathlib import Path

PACKAGES = (
    "pydantic",
    "pydantic_core",
    "PyJWT",
    "cryptography",
    "cffi",
    "pycparser",
    "annotated-types",
    "typing_extensions",
    "typing-inspection",
    "PyInstaller",
    "pyinstaller-hooks-contrib",
    "PySide6-Essentials",
    "shiboken6",
    "packaging",
    "altgraph",
    "pefile",
    "pywin32-ctypes",
)


def main() -> None:
    dest = Path("dist/VoxPreview/licenses")
    dest.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        try:
            distribution = metadata.distribution(package)
        except metadata.PackageNotFoundError:
            continue
        files = distribution.files or []
        license_files = [
            f for f in files if "license" in str(f).lower() or "copying" in str(f).lower()
        ]
        output = dest / package
        for file in license_files:
            source = Path(distribution.locate_file(file))
            if source.is_file() and (".dist-info" in str(file) or "licenses" in str(file).lower()):
                output.mkdir(exist_ok=True)
                shutil.copy2(source, output / source.name)
    for source in Path("installer/licenses").iterdir():
        if source.is_file():
            shutil.copy2(source, dest / source.name)
    shutil.copy2("installer/README.txt", "dist/VoxPreview/README.txt")
    shutil.copy2("NOTICE.md", "dist/VoxPreview/NOTICE.md")


if __name__ == "__main__":
    main()
