"""Generates PyInstaller version_info.txt from github_harvester.version."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_harvester.version import (
    APP_DISPLAY_NAME,
    APP_NAME,
    AUTHOR,
    COPYRIGHT,
    CURRENT_SEMVER,
    __version__,
)

pe_tuple = CURRENT_SEMVER.to_pe_tuple()

VERSION_INFO_TEMPLATE = f"""# UTF-8
#
# VSVersionInfo structure for Windows PE executable
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={pe_tuple},
    prodvers={pe_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', '{AUTHOR}'),
            StringStruct('FileDescription', '{APP_DISPLAY_NAME}'),
            StringStruct('FileVersion', '{__version__}'),
            StringStruct('InternalName', '{APP_NAME}'),
            StringStruct('LegalCopyright', '{COPYRIGHT}'),
            StringStruct('OriginalFilename', '{APP_NAME}.exe'),
            StringStruct('ProductName', '{APP_DISPLAY_NAME}'),
            StringStruct('ProductVersion', '{__version__}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def generate_version_info(target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(VERSION_INFO_TEMPLATE, encoding="utf-8")
    return target_path


if __name__ == "__main__":
    out_file = ROOT / "_build" / "version_info.txt"
    generate_version_info(out_file)
    print(f"Generated Windows PE version info at: {out_file}")
