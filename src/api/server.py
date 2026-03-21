"""
FastAPI backend for C_manager.
Exposes scan, explain, and progress endpoints.
Port: 8765
"""
import asyncio
import json
import os
import time
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.scanner.scanner import ScanItem, get_drive_info, scan_directory
from src.analyzer.analyzer import explain_with_llm, format_size, rate_safety

app = FastAPI(title="C_manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory scan state (single-user desktop app)
_scan_state: dict = {
    "running": False,
    "progress": 0,
    "current_path": "",
    "results": [],
    "error": None,
}


# ─── Request/Response Models ───────────────────────────────────────────────────

class ScanRequest(BaseModel):
    root: str = "C:\\"
    min_size_mb: float = 10.0
    max_depth: int = 3


class ExplainRequest(BaseModel):
    path: str
    size_bytes: int
    is_dir: bool
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "anthropic/claude-haiku-4-5"


class ScanResultItem(BaseModel):
    path: str
    name: str
    size: int
    size_human: str
    is_dir: bool
    children_count: int
    safety: str


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/drive-info")
def drive_info(drive: str = "C:\\"):
    return get_drive_info(drive)


@app.post("/api/scan")
async def start_scan(req: ScanRequest):
    """Start a background scan and return immediately."""
    global _scan_state
    if _scan_state["running"]:
        raise HTTPException(status_code=409, detail="Scan already running")

    _scan_state = {
        "running": True,
        "progress": 0,
        "current_path": "",
        "results": [],
        "error": None,
    }

    asyncio.create_task(_run_scan(req))
    return {"status": "started"}


async def _run_scan(req: ScanRequest) -> None:
    global _scan_state
    loop = asyncio.get_event_loop()
    min_bytes = int(req.min_size_mb * 1024 * 1024)

    def progress_cb(count: int, path: str) -> None:
        _scan_state["progress"] = count
        _scan_state["current_path"] = path

    try:
        items: list[ScanItem] = await loop.run_in_executor(
            None,
            lambda: scan_directory(req.root, min_bytes, req.max_depth, progress_cb),
        )
        results = []
        for item in items:
            results.append({
                "path": item.path,
                "name": item.name,
                "size": item.size,
                "size_human": format_size(item.size),
                "is_dir": item.is_dir,
                "children_count": item.children_count,
                "safety": rate_safety(item.path),
            })
        _scan_state["results"] = results
    except Exception as e:
        _scan_state["error"] = str(e)
    finally:
        _scan_state["running"] = False


@app.get("/api/scan/progress")
async def scan_progress():
    """SSE stream: sends progress updates until scan completes."""
    async def event_stream() -> AsyncGenerator[str, None]:
        while True:
            state = _scan_state
            data = json.dumps({
                "running": state["running"],
                "progress": state["progress"],
                "current_path": state["current_path"],
                "result_count": len(state["results"]),
                "error": state["error"],
            })
            yield f"data: {data}\n\n"
            if not state["running"]:
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/scan/results")
def scan_results():
    """Return current scan results."""
    return {
        "running": _scan_state["running"],
        "results": _scan_state["results"],
        "error": _scan_state["error"],
    }


@app.post("/api/explain")
async def explain_item(req: ExplainRequest):
    """Call LLM to explain a file/folder."""
    safety = rate_safety(req.path)
    size_human = format_size(req.size_bytes)
    try:
        explanation = await explain_with_llm(
            path=req.path,
            size_human=size_human,
            is_dir=req.is_dir,
            safety=safety,
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")
    return {
        "path": req.path,
        "safety": safety,
        "size_human": size_human,
        "explanation": explanation,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="127.0.0.1", port=8765, reload=False)
