"""Add `renderer/src/` to sys.path so tests can import `latex_pipeline`."""
import os, sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
