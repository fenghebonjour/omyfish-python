import sys
from pathlib import Path

# Tests import project modules from the repo root (same convention as
# `python -m` module mode used by the Makefile targets).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
