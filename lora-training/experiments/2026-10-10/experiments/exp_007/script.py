"""Execute this pre-registered experiment through the shared bounded NF4 runner."""
import runpy
import sys
from pathlib import Path
if __name__ == '__main__':
    directory = Path(__file__).resolve().parent
    sys.argv[1:1] = ['--experiment', directory.name]
    runpy.run_path(str(directory.parents[1] / 'training.py'), run_name='__main__')
