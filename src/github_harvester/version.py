"""Application version and metadata (Single Source of Truth)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

__version__ = "1.1.1"
APP_NAME = "GithubSearchDownloader"
APP_DISPLAY_NAME = "GitHub Search & Downloader"
AUTHOR = "Nikita Kizevich"
COPYRIGHT = "Copyright (c) 2026 Nikita Kizevich. All rights reserved."
REPO_OWNER = "AI-Nikitka93"
REPO_NAME = "github-search-downloader"
GITHUB_REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

SEMVER_REGEX = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def _compare_prerelease(pre_a: str, pre_b: str) -> int:
    """SemVer 2.0.0 Section 11 dot-separated pre-release identifier comparison."""
    parts_a = pre_a.split(".")
    parts_b = pre_b.split(".")

    for a, b in zip(parts_a, parts_b):
        if a == b:
            continue
        a_is_num = a.isdigit()
        b_is_num = b.isdigit()

        if a_is_num and b_is_num:
            val_a = int(a)
            val_b = int(b)
            if val_a != val_b:
                return -1 if val_a < val_b else 1
        elif a_is_num and not b_is_num:
            return -1
        elif not a_is_num and b_is_num:
            return 1
        else:
            return -1 if a < b else 1

    len_a = len(parts_a)
    len_b = len(parts_b)
    if len_a != len_b:
        return -1 if len_a < len_b else 1
    return 0


@dataclass(frozen=True, order=False)
class SemVer:
    """Semantic Versioning 2.0.0 parser and comparator."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    buildmetadata: str = ""

    @classmethod
    def parse(cls, version_str: str) -> SemVer:
        match = SEMVER_REGEX.match(version_str.strip())
        if not match:
            raise ValueError(f"Invalid SemVer 2.0.0 string: {version_str!r}")
        data = match.groupdict()
        return cls(
            major=int(data["major"]),
            minor=int(data["minor"]),
            patch=int(data["patch"]),
            prerelease=data["prerelease"] or "",
            buildmetadata=data["buildmetadata"] or "",
        )

    def to_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    @property
    def build(self) -> str:
        return self.buildmetadata

    def to_pe_tuple(self) -> tuple[int, int, int, int]:
        """Returns 4-integer tuple for Windows PE VS_VERSION_INFO."""
        return (self.major, self.minor, self.patch, 0)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base = f"{base}-{self.prerelease}"
        if self.buildmetadata:
            base = f"{base}+{self.buildmetadata}"
        return base

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        if self.to_tuple() != other.to_tuple():
            return self.to_tuple() < other.to_tuple()
        # Normal version has higher precedence than prerelease
        if self.prerelease and not other.prerelease:
            return True
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and other.prerelease:
            return _compare_prerelease(self.prerelease, other.prerelease) < 0
        return False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.to_tuple() == other.to_tuple() and self.prerelease == other.prerelease

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return not (self <= other)

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return not (self < other)


CURRENT_SEMVER = SemVer.parse(__version__)
