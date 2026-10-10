"""Run this frozen experiment with the shared bounded inference implementation."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    path = Path(__file__).resolve()
    sys.argv = [str(path.parents[2] / "inference.py"), "--experiment", path.parent.name]
    runpy.run_path(sys.argv[0], run_name="__main__")
