"""Response models for the LLM analyzer."""

from dataclasses import dataclass
from enum import Enum


class SafetyRating(str, Enum):
    SAFE = "safe"        # 🟢 Safe to delete
    CAUTION = "caution"  # 🟡 Keep recommended
    DANGER = "danger"    # 🔴 System core, do not touch
    UNKNOWN = "unknown"  # Cannot determine


@dataclass
class AnalysisResult:
    explanation: str          # Casual Chinese explanation
    safety_rating: SafetyRating
    confidence: float         # 0.0 to 1.0
    cached: bool = False      # True if result came from cache
