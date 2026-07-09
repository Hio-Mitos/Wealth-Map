#!/usr/bin/env python3
"""
WealthMap – Personal & Business Finance Manager
================================================
Local-first: all data stored in SQLite on your machine.
Run:  python main.py
"""

import sys
import os
from pathlib import Path

# ── Resolve project root so imports work from any working directory ────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Data root: ~/WealthMap (configurable via env var) ───────────────────────────
# Each profile (Personal or Business) gets its own subdirectory under
# <DATA_ROOT>/profiles/<id>/ with its own database and attachments folder.
DATA_ROOT = os.environ.get("WEALTHMAP_DATA", str(Path.home() / "WealthMap"))


def main():
    from src.services.profiles import ProfileRegistry
    from src.services.core import AppContext
    from src.ui.launcher import ProfileLauncher
    from src.ui.app import WealthMapApp

    registry = ProfileRegistry(DATA_ROOT)
    target_profile_id = None  # set when switching directly from within the app

    while True:
        if target_profile_id:
            profile = registry.get_profile(target_profile_id)
            target_profile_id = None
        else:
            launcher = ProfileLauncher(registry)
            launcher.mainloop()
            profile = launcher.selected_profile
            _safe_destroy(launcher)

        if profile is None:
            break  # window closed without choosing a profile -> exit

        data_dir = registry.data_dir(profile["id"])
        ctx = AppContext(str(data_dir), profile=profile, registry=registry)
        app = WealthMapApp(ctx)
        app.mainloop()

        next_target = getattr(app, "target_profile_id", None)
        switch_requested = getattr(app, "switch_profile_requested", False)
        _safe_destroy(app)

        if next_target:
            target_profile_id = next_target
        elif not switch_requested:
            break


def _safe_destroy(window):
    """
    Best-effort cleanup after a window's mainloop has already exited via
    quit() (which is what matters for control flow). destroy() can raise on
    some platforms/CustomTkinter versions when called on an already-withdrawn
    window with pending internal `after` callbacks — that's fine to ignore
    here since the window is hidden either way and the process is moving on
    to the next window.
    """
    try:
        window.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
