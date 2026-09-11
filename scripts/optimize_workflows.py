#!/usr/bin/env python3
"""Compatibility entry point: validate the canonical 2.5 workflows.

The historical optimizer required obsolete source graphs. Since release 2.5 the
reviewed layouts ARE the canonical examples; regenerating from them would duplicate
mastering nodes. Edit the canonical JSON directly and validate it instead.
"""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print("The optimized layouts are now canonical. Validating without rewriting files.", flush=True)
    subprocess.run([sys.executable, str(root / "scripts" / "validate_release.py")], cwd=root, check=True)
