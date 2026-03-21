"""Data models for the disk scanner."""

from dataclasses import dataclass, field
from enum import Enum


class SafetyRating(str, Enum):
    SAFE = "safe"        # 🟢 Safe to delete
    CAUTION = "caution"  # 🟡 Keep recommended
    DANGER = "danger"    # 🔴 System core, do not touch
    UNKNOWN = "unknown"  # No rating available


@dataclass
class FileInfo:
    path: str
    size_bytes: int
    is_dir: bool
    last_modified: float        # Unix timestamp
    extension: str              # e.g. ".tmp", "" for dirs/no-ext
    safety_rating: SafetyRating = SafetyRating.UNKNOWN
    safety_reason: str = ""

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 * 1024 * 1024)
