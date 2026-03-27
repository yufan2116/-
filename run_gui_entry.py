"""
PyInstaller GUI entry wrapper.

Why:
- `src/multi_video_dl/gui.py` uses package-relative imports (e.g. `.core...`).
- When PyInstaller treats a module as a script, those relative imports can break.

This wrapper forces `src/` onto `sys.path` and then calls the GUI `main()`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

# Ensure `multi_video_dl` package is importable.
sys.path.insert(0, str(SRC))

from multi_video_dl.gui import main  # noqa: E402


if __name__ == "__main__":
    main()

