"""Allow ``python -m dtsound`` from the pipeline directory."""
from __future__ import annotations

from .generate import main

if __name__ == "__main__":
    raise SystemExit(main())
