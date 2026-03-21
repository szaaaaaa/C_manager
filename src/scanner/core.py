"""
File system scanner — fast directory traversal using os.scandir.
Returns a list of entries sorted by size descending.
SAFETY: read-only, never modifies any files.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileEntry:
    name: str
    path: str
    is_dir: bool
    size: int          # bytes; for dirs this is the total subtree size
    child_count: int   # number of immediate children (0 for files)
    error: Optional[str] = None  # set if we couldn't stat the entry


@dataclass
class ScanResult:
    root: str
    entries: list[FileEntry] = field(default_factory=list)
    total_size: int = 0
    error: Optional[str] = None


def _entry_size(de: os.DirEntry) -> tuple[int, int]:
    """Return (size_bytes, child_count) for a single DirEntry.
    For directories, size is the immediate-children total (shallow).
    """
    try:
        if de.is_dir(follow_symlinks=False):
            total = 0
            count = 0
            try:
                with os.scandir(de.path) as inner:
                    for child in inner:
                        count += 1
                        try:
                            if child.is_file(follow_symlinks=False):
                                total += child.stat(follow_symlinks=False).st_size
                            elif child.is_dir(follow_symlinks=False):
                                total += _deep_size(child.path)
                        except (PermissionError, OSError):
                            pass
            except (PermissionError, OSError):
                pass
            return total, count
        else:
            return de.stat(follow_symlinks=False).st_size, 0
    except (PermissionError, OSError):
        return 0, 0


def _deep_size(path: str) -> int:
    """Recursively compute total size of a directory subtree."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _deep_size(entry.path)
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


def scan_directory(path: str, top_n: int = 50) -> ScanResult:
    """Scan *path* and return its top-level entries sorted by size descending.

    Args:
        path: Absolute path to scan.
        top_n: Maximum number of entries to return (largest first).

    Returns:
        ScanResult with entries sorted by size descending.
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        return ScanResult(root=abs_path, error=f"Path does not exist: {abs_path}")

    if not os.path.isdir(abs_path):
        return ScanResult(root=abs_path, error=f"Not a directory: {abs_path}")

    entries: list[FileEntry] = []
    total_size = 0

    try:
        with os.scandir(abs_path) as it:
            for de in it:
                size, child_count = _entry_size(de)
                total_size += size
                entries.append(FileEntry(
                    name=de.name,
                    path=de.path,
                    is_dir=de.is_dir(follow_symlinks=False),
                    size=size,
                    child_count=child_count,
                ))
    except PermissionError as exc:
        return ScanResult(root=abs_path, error=f"Permission denied: {exc}")
    except OSError as exc:
        return ScanResult(root=abs_path, error=str(exc))

    entries.sort(key=lambda e: e.size, reverse=True)
    return ScanResult(root=abs_path, entries=entries[:top_n], total_size=total_size)
