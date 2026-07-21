"""
WealthMap – Profile Registry
Manages multiple Personal/Business profiles, each with its own data
directory (own SQLite database + attachments folder), and the "linked"
relationships between same-type profiles used for cross-profile transfers.
"""

import os
import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict

PROFILE_TYPES = ["personal", "business"]


class ProfileRegistry:
    """
    Persists profile metadata to <root>/profiles.json:
      {
        "profiles": [
          {"id": "...", "name": "...", "type": "personal"|"business",
           "linked": ["id2", ...], "created_at": "..."}
        ],
        "last_opened": "id" | null
      }

    Each profile's data lives in <root>/profiles/<id>/ (wealthmap.db +
    attachments/).
    """

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "profiles.json"
        self._load()
        self._migrate_legacy()

    # ── Persistence ──────────────────────────────────────────────────────

    def reload(self):
        """Re-reads profiles.json from disk and re-runs the legacy-install
        migration check. Used after something external to this instance
        changed the data root — e.g. a Google Drive restore just wrote a
        new profiles.json/profiles/ directly onto disk."""
        self._load()
        self._migrate_legacy()

    def _load(self):
        if self.registry_path.exists():
            try:
                self.data = json.loads(self.registry_path.read_text())
            except Exception:
                self.data = {"profiles": [], "last_opened": None}
        else:
            self.data = {"profiles": [], "last_opened": None}
        self.data.setdefault("profiles", [])
        self.data.setdefault("last_opened", None)

    def _save(self):
        self.registry_path.write_text(json.dumps(self.data, indent=2))

    def _migrate_legacy(self):
        """
        If this is an upgrade from a single-profile install (a
        wealthmap.db sitting directly in <root>), copy it into a new
        "Personal" profile so existing users don't lose data.

        Uses copy-then-cleanup rather than move: on Windows the old db file
        is sometimes still briefly locked (by this process's own prior
        connection, an antivirus scan, etc.), which would make a plain
        `shutil.move` raise PermissionError on the final unlink step *after*
        the copy already succeeded. We don't want that to crash startup or
        leave the user thinking their data is gone — so the copy is the
        part that matters, and removing the old files afterward is just a
        best-effort tidy-up.
        """
        legacy_db = self.root / "wealthmap.db"
        if self.data["profiles"] or not legacy_db.exists():
            return

        profile = self.create_profile("Personal", "personal", _skip_dirs=True)
        new_dir = self.data_dir(profile["id"])
        new_dir.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(legacy_db), str(new_dir / "wealthmap.db"))
            # SQLite WAL-mode sidecar files, if present
            for suffix in ("-wal", "-shm"):
                sidecar = self.root / f"wealthmap.db{suffix}"
                if sidecar.exists():
                    shutil.copy2(str(sidecar), str(new_dir / f"wealthmap.db{suffix}"))
        except Exception as e:
            # Copy itself failed — undo the profile we just created so
            # migration is retried (cleanly) on the next launch.
            print(f"[Profile migration] Failed to copy database: {e}")
            self.data["profiles"] = [p for p in self.data["profiles"] if p["id"] != profile["id"]]
            self._save()
            shutil.rmtree(new_dir, ignore_errors=True)
            return

        legacy_attachments = self.root / "attachments"
        att_dest = new_dir / "attachments"
        if legacy_attachments.exists():
            try:
                shutil.copytree(str(legacy_attachments), str(att_dest), dirs_exist_ok=True)
            except Exception as e:
                print(f"[Profile migration] Failed to copy attachments: {e}")
                att_dest.mkdir(parents=True, exist_ok=True)
        else:
            att_dest.mkdir(parents=True, exist_ok=True)

        self.set_last_opened(profile["id"])

        # Best-effort cleanup of the old files — failures here (e.g. a
        # locked file on Windows) are fine; the data has already been
        # safely copied above.
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(str(self.root / f"wealthmap.db{suffix}"))
            except Exception:
                pass
        if legacy_attachments.exists():
            try:
                shutil.rmtree(str(legacy_attachments))
            except Exception:
                pass

    # ── Profile CRUD ─────────────────────────────────────────────────────

    def list_profiles(self, type_filter: Optional[str] = None) -> List[Dict]:
        profiles = self.data["profiles"]
        if type_filter:
            profiles = [p for p in profiles if p["type"] == type_filter]
        return profiles

    def get_profile(self, profile_id: str) -> Optional[Dict]:
        return next((p for p in self.data["profiles"] if p["id"] == profile_id), None)

    def create_profile(self, name: str, ptype: str, _skip_dirs: bool = False) -> Dict:
        if ptype not in PROFILE_TYPES:
            raise ValueError(f"Profile type must be one of {PROFILE_TYPES}")
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")
        profile = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "type": ptype,
            "linked": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.data["profiles"].append(profile)
        self._save()
        if not _skip_dirs:
            d = self.data_dir(profile["id"])
            d.mkdir(parents=True, exist_ok=True)
            (d / "attachments").mkdir(parents=True, exist_ok=True)
        return profile

    def rename_profile(self, profile_id: str, new_name: str):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Profile name cannot be empty")
        p = self.get_profile(profile_id)
        if p:
            p["name"] = new_name
            self._save()

    def delete_profile(self, profile_id: str, delete_files: bool = True):
        p = self.get_profile(profile_id)
        if not p:
            return
        # Unlink from any profiles that reference this one
        for other in self.data["profiles"]:
            if profile_id in other.get("linked", []):
                other["linked"].remove(profile_id)
        self.data["profiles"] = [pr for pr in self.data["profiles"] if pr["id"] != profile_id]
        if self.data.get("last_opened") == profile_id:
            self.data["last_opened"] = None
        self._save()
        if delete_files:
            d = self.data_dir(profile_id)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    # ── Linking (same-type only) ────────────────────────────────────────

    def link(self, id1: str, id2: str):
        p1, p2 = self.get_profile(id1), self.get_profile(id2)
        if not p1 or not p2:
            raise ValueError("Profile not found")
        if p1["type"] != p2["type"]:
            raise ValueError("Only profiles of the same type can be linked")
        if id1 == id2:
            raise ValueError("A profile can't be linked to itself")
        if id2 not in p1["linked"]:
            p1["linked"].append(id2)
        if id1 not in p2["linked"]:
            p2["linked"].append(id1)
        self._save()

    def unlink(self, id1: str, id2: str):
        p1, p2 = self.get_profile(id1), self.get_profile(id2)
        if p1 and id2 in p1.get("linked", []):
            p1["linked"].remove(id2)
        if p2 and id1 in p2.get("linked", []):
            p2["linked"].remove(id1)
        self._save()

    def linked_profiles(self, profile_id: str) -> List[Dict]:
        p = self.get_profile(profile_id)
        if not p:
            return []
        return [pr for pr in (self.get_profile(lid) for lid in p.get("linked", [])) if pr]

    def linkable_profiles(self, profile_id: str) -> List[Dict]:
        """Other profiles of the same type, not yet linked."""
        p = self.get_profile(profile_id)
        if not p:
            return []
        linked = set(p.get("linked", []))
        return [pr for pr in self.data["profiles"]
                if pr["id"] != profile_id and pr["type"] == p["type"] and pr["id"] not in linked]

    # ── Paths ────────────────────────────────────────────────────────────

    def data_dir(self, profile_id: str) -> Path:
        return self.root / "profiles" / profile_id

    def db_path(self, profile_id: str) -> Path:
        return self.data_dir(profile_id) / "wealthmap.db"

    def set_last_opened(self, profile_id: Optional[str]):
        self.data["last_opened"] = profile_id
        self._save()

    def get_last_opened(self) -> Optional[Dict]:
        pid = self.data.get("last_opened")
        return self.get_profile(pid) if pid else None


def list_remote_accounts(db_path) -> List[Dict]:
    """
    Lightweight, read-only listing of a *different* profile's active
    accounts (id, name, currency code/symbol) via a direct sqlite3
    connection — used to populate "also affects account" pickers without
    the overhead of spinning up a full AppContext just to browse accounts.
    """
    import sqlite3
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.id, a.name, c.code, c.symbol
                FROM accounts a JOIN currencies c ON a.currency_id = c.id
                WHERE a.is_active = 1
                ORDER BY a.name
            """)
            return [{"id": r[0], "name": r[1], "currency_code": r[2], "currency_symbol": r[3]}
                    for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []
