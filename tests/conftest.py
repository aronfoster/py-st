# tests/conftest.py
import sys
from pathlib import Path

# Add <repo>/src to sys.path so `import py_st` works in tests
root = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(root))
