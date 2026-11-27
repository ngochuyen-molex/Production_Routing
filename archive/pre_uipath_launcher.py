"""Run before the UiPath routing automation: routing condition -> alt BOM count.

    python pre_uipath.py FILE        (or: routing pre-uipath FILE)

ARCHIVED 2026-11-27: was the repo-root pre_uipath.py (shim for UiPath / VBS). Does not run from
archive/; restore it to the repo root together with archive/pre_uipath.py and the CLI command.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    from routing.cli import legacy_script
    legacy_script("pre-uipath")
