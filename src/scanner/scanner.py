"""
File system scanner — READ ONLY, never deletes or modifies anything.
Uses os.scandir() for fast traversal.
"""
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Generator, Optional


@dataclass
class ScanItem:
    path: str
    name: str
    size: int          # bytes
    is_dir: bool
    children_count: int = 0
    error: Optional[str] = None


def _get_dir_size(path: str, progress_cb: Optional[Callable] = None) -> tuple[int, int]:
    """Recursively sum a directory's size. Returns (total_bytes, file_count)."""
    total = 0
    count = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        sub_size, sub_count = _get_dir_size(entry.path, progress_cb)
                        total += sub_size
                        count += sub_count
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total, count


def scan_directory(
    root: str,
    min_size_bytes: int = 1024 * 1024,  # 1 MB default
    max_depth: int = 3,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> list[ScanItem]:
    """
    Scan root directory up to max_depth, returning items above min_size_bytes.
    READ ONLY — never modifies the filesystem.
    """
    results: list[ScanItem] = []
    scanned_count = 0

    def _scan(path: str, depth: int) -> None:
        nonlocal scanned_count
        if depth > max_depth:
            return
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except (PermissionError, OSError):
            return

        for entry in entries:
            scanned_count += 1
            if progress_cb and scanned_count % 100 == 0:
                progress_cb(scanned_count, entry.path)

            try:
                if entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    if stat.st_size >= min_size_bytes:
                        results.append(ScanItem(
                            path=entry.path,
                            name=entry.name,
                            size=stat.st_size,
                            is_dir=False,
                        ))
                elif entry.is_dir(follow_symlinks=False):
                    dir_size, dir_count = _get_dir_size(entry.path, progress_cb)
                    if dir_size >= min_size_bytes:
                        results.append(ScanItem(
                            path=entry.path,
                            name=entry.name,
                            size=dir_size,
                            is_dir=True,
                            children_count=dir_count,
                        ))
                    # Recurse only if at shallow depth
                    if depth < max_depth:
                        _scan(entry.path, depth + 1)
            except (PermissionError, OSError) as e:
                pass

    _scan(root, depth=1)
    results.sort(key=lambda x: x.size, reverse=True)
    return results


def get_drive_info(drive: str = "C:\\") -> dict:
    """Return total/used/free bytes for a drive. READ ONLY."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(drive)
        return {"drive": drive, "total": total, "used": used, "free": free}
    except Exception as e:
        return {"drive": drive, "total": 0, "used": 0, "free": 0, "error": str(e)}
