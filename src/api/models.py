"""Pydantic request/response models for the FastAPI server."""

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    root: str = "C:\\"
    min_size_mb: float = Field(default=50.0, ge=0.0)
    max_depth: int = Field(default=4, ge=0)


class FileInfoResponse(BaseModel):
    path: str
    size_bytes: int
    size_mb: float
    is_dir: bool
    extension: str
    safety_rating: str
    safety_reason: str


class ScanResponse(BaseModel):
    root: str
    total_items: int
    items: list[FileInfoResponse]


class ExplainRequest(BaseModel):
    path: str
    size_bytes: int
    is_dir: bool
    parent_folder: str = ""


class ExplainResponse(BaseModel):
    path: str
    explanation: str
    safety_rating: str
    confidence: float
    cached: bool


class ConfigResponse(BaseModel):
    llm_model: str
    llm_provider: str
    scanner_default_root: str
    scanner_min_size_mb: float
    scanner_max_depth: int
