"""
WealthMap – Google Drive Backup Service
=========================================
Backs up the *entire* data root (profiles.json + every profile's database
and attachments — i.e. everything under WEALTHMAP_DATA / ~/WealthMap) to a
dedicated "WealthMap Backups" folder in the user's own Google Drive, so it
can be restored on a new PC.

Design notes
------------
* True in-app Google Drive integration (OAuth "installed app" flow) — no
  Google Drive desktop client required. Two ways to connect:
    - "Quick Connect": uses a shared OAuth client bundled with the app
      (see BUNDLED_CLIENT_SECRET_PATH) so a colleague never has to touch
      Google Cloud Console — just sign in with their own Google account.
      Someone administering WealthMap sets this bundled client up once.
    - "Advanced": bring your own `client_secret.json` from your own
      Google Cloud project, for anyone who'd rather not share a client.
  Either way, each person authorizes access to *their own* Drive — the
  shared client is just an app identity, not a shared account.
* Backups are a single encrypted archive: zip the data root, then encrypt
  it with a key derived (PBKDF2-HMAC-SHA256, 390k iterations) from a
  password. The *password itself is never stored* — only a random salt
  and a small "verifier" (a known string encrypted with the derived key)
  so a supplied password can be checked before attempting a real restore.
  Anyone with access to the Drive files alone (Google included) cannot
  read the backup contents.
* Two ways to get that password:
    - Manual: the user picks one and re-enters it once per app session
      to unlock automatic backups (nothing is ever written to disk).
    - Auto-generated ("recovery key"): WealthMap generates a strong
      random one, stores it in the OS's own secure credential store
      (Windows Credential Manager / macOS Keychain / Linux Secret
      Service, via the `keyring` package) so this PC never has to ask
      again, and shows it to the user exactly once so they can save it
      for restoring on a *different* PC (where there's no OS credential
      entry to read it back from). This is the WhatsApp/Signal-style
      "recovery key" pattern, and is what Quick Connect uses by default.
  Both modes reuse the exact same salt/verifier/encryption machinery —
  an auto-generated key is treated as just a very strong password that
  happens to be remembered for you instead of typed by you.
* Config (which triggers are enabled, the connection state, the password
  salt/verifier, last backup time) lives in `<data_root>/backup_config.json`.
  The OAuth token lives in `<data_root>/gdrive_token.json`. Neither file
  contains the backup password/recovery key.
"""

import base64
import json
import os
import secrets
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Google API client libraries (and `keyring`) are imported lazily inside
# the methods that need them, so the rest of the app (and any environment
# without these packages installed) doesn't fail just importing this module.

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BACKUP_FOLDER_NAME = "WealthMap Backups"
VERIFIER_PLAINTEXT = b"WEALTHMAP-BACKUP-OK"
KDF_ITERATIONS = 390_000
DEFAULT_RETAIN = 10
DEBOUNCE_SECONDS = 90
DAILY_SECONDS = 24 * 60 * 60

ALL_TRIGGERS = ("on_change", "daily", "on_close")
DEFAULT_QUICK_CONNECT_TRIGGERS = ["on_change", "on_close"]

# The shared, app-wide OAuth client for "Quick Connect". This is *not* a
# per-user secret — it identifies the WealthMap application to Google, the
# way any desktop app's client ID does; each person who connects still
# authorizes only their own Drive. Whoever administers/distributes
# WealthMap creates this once in Google Cloud Console and places the
# downloaded JSON at this path (kept out of version control — see
# .gitignore). If it isn't present, Quick Connect simply isn't offered and
# people fall back to the "Advanced" bring-your-own-client flow.
BUNDLED_CLIENT_SECRET_PATH = Path(__file__).resolve().parent.parent.parent / "gdrive_bundled_client.json"

KEYRING_SERVICE = "WealthMap-GoogleDriveBackup"


class BackupError(Exception):
    pass


class WrongPassword(BackupError):
    pass


# ─── Config (non-secret state, on disk) ────────────────────────────────────

class BackupConfig:
    """Persists backup settings to <data_root>/backup_config.json.
    Never stores the password itself — only a salt + verifier used to
    check a password the user re-enters."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "backup_config.json"
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except Exception:
                self.data = {}
        else:
            self.data = {}
        self.data.setdefault("triggers", [])          # subset of ALL_TRIGGERS
        self.data.setdefault("folder_id", None)
        self.data.setdefault("last_backup_at", None)
        self.data.setdefault("last_backup_error", None)
        self.data.setdefault("retain_count", DEFAULT_RETAIN)
        self.data.setdefault("password_salt", None)    # base64
        self.data.setdefault("password_verifier", None)  # base64 (encrypted known string)
        self.data.setdefault("client_secret_path", None)
        self.data.setdefault("connect_mode", None)       # "quick" | "advanced"
        self.data.setdefault("key_mode", None)           # "auto" | "manual"

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    @property
    def has_password(self) -> bool:
        return bool(self.data.get("password_salt") and self.data.get("password_verifier"))

    @property
    def triggers(self) -> List[str]:
        return list(self.data.get("triggers", []))

    def set_triggers(self, triggers: List[str]):
        self.set("triggers", [t for t in triggers if t in ALL_TRIGGERS])


# ─── Password / encryption helpers ─────────────────────────────────────────

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=KDF_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


class GoogleDriveBackupService:
    def __init__(self, registry, on_status: Optional[Callable[[str], None]] = None):
        """`registry` is a ProfileRegistry (gives us .root, the data dir
        containing profiles.json + profiles/). `on_status` is an optional
        callback(str) used to surface progress/errors to the UI thread."""
        self.registry = registry
        self.root = Path(registry.root)
        self.config = BackupConfig(self.root)
        self.token_path = self.root / "gdrive_token.json"
        self._on_status = on_status or (lambda msg: None)

        # In-memory only — never persisted. Unlocked once per session.
        self._session_key: Optional[bytes] = None

        self._lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._running = False

    # ── Status helper ────────────────────────────────────────────────────

    def set_status_callback(self, on_status: Optional[Callable[[str], None]]):
        """Lets the currently-open Settings panel (if any) receive live
        progress text ("Creating backup archive…", "Uploading…", etc.)
        for the manual progress bar / status line. Safe to call repeatedly
        (e.g. each time the panel rebuilds) — always replaces, not stacks."""
        self._on_status = on_status or (lambda msg: None)

    @property
    def is_running(self) -> bool:
        return self._running

    def _status(self, msg: str):
        try:
            self._on_status(msg)
        except Exception:
            pass

    # ── Password lifecycle ──────────────────────────────────────────────

    def set_password(self, password: str, key_mode: str = "manual"):
        """(Re)sets the backup password. Existing backups made with the
        old password are unaffected (still need the old password to
        restore them) — only backups made from now on use the new one.
        `key_mode` is just recorded for display ("manual" = user-chosen,
        re-entered each session; "auto" = generated + kept in the OS
        credential store, see generate_and_store_key)."""
        salt = os.urandom(16)
        key = _derive_key(password, salt)
        verifier = Fernet(key).encrypt(VERIFIER_PLAINTEXT)
        self.config.data["password_salt"] = base64.b64encode(salt).decode()
        self.config.data["password_verifier"] = base64.b64encode(verifier).decode()
        self.config.data["key_mode"] = key_mode
        self.config.save()
        self._session_key = key  # unlock this session immediately too

    # ── Auto-generated recovery key (OS credential store) ────────────────
    # Lets a fully-automatic setup (Quick Connect) work without ever
    # prompting for a password on the machine that generated it, while
    # still producing something the person can save and use to restore on
    # a different machine — the recovery key *is* the password, just
    # picked and remembered for them instead of typed by them.

    def _keyring_username(self) -> str:
        # Scoped to this data root so multiple WealthMap data directories
        # on one machine (unusual, but possible via WEALTHMAP_DATA) don't
        # collide in the OS credential store.
        return str(self.root)

    def generate_and_store_key(self) -> str:
        """Generates a strong random recovery key, sets it as the backup
        password (auto mode), and saves it in the OS's secure credential
        store so this machine can retrieve it silently from now on.
        Returns the generated key — the ONLY time it's available in full;
        show it to the user immediately so they can save it themselves
        for restoring on a different PC."""
        try:
            import keyring
        except ImportError as e:
            raise BackupError(
                "Secure credential storage isn't installed. Run:\n"
                "  pip install keyring"
            ) from e

        recovery_key = secrets.token_urlsafe(24)  # ~32 chars, high entropy
        self.set_password(recovery_key, key_mode="auto")
        try:
            keyring.set_password(KEYRING_SERVICE, self._keyring_username(), recovery_key)
        except Exception as e:
            raise BackupError(f"Couldn't save the recovery key securely on this PC: {e}") from e
        return recovery_key

    def try_silent_unlock(self) -> bool:
        """If this machine has an auto-generated key saved in its OS
        credential store, retrieves and verifies it with no user
        interaction. Returns True if that unlocked the session."""
        if self.is_unlocked:
            return True
        if self.config.get("key_mode") != "auto" or not self.config.has_password:
            return False
        try:
            import keyring
            stored = keyring.get_password(KEYRING_SERVICE, self._keyring_username())
        except Exception:
            return False
        if not stored:
            return False
        try:
            return self.verify_and_unlock(stored)
        except BackupError:
            return False

    def _forget_stored_key(self):
        if self.config.get("key_mode") != "auto":
            return
        try:
            import keyring
            keyring.delete_password(KEYRING_SERVICE, self._keyring_username())
        except Exception:
            pass

    def verify_and_unlock(self, password: str) -> bool:
        """Checks `password` against the stored verifier; if correct,
        caches the derived key in memory for this session and returns
        True. Never writes the password anywhere."""
        if not self.config.has_password:
            raise BackupError("No backup password has been set yet.")
        salt = base64.b64decode(self.config.data["password_salt"])
        verifier = base64.b64decode(self.config.data["password_verifier"])
        key = _derive_key(password, salt)
        try:
            Fernet(key).decrypt(verifier)
        except InvalidToken:
            return False
        self._session_key = key
        return True

    @property
    def is_unlocked(self) -> bool:
        return self._session_key is not None

    def lock(self):
        self._session_key = None

    # ── Google OAuth ─────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self.token_path.exists()

    @staticmethod
    def is_bundled_client_available() -> bool:
        """Whether whoever administers this WealthMap install has placed
        the shared OAuth client needed for one-click Quick Connect."""
        return BUNDLED_CLIENT_SECRET_PATH.is_file()

    def connect(self, client_secret_path: str, mode: str = "advanced"):
        """Runs the OAuth 'installed app' consent flow (opens the user's
        browser). Blocking — call from a background thread. Raises
        BackupError on failure. `mode` is just recorded for display
        ("quick" = bundled shared client, "advanced" = the user's own)."""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as e:
            raise BackupError(
                "Google Drive support isn't installed. Run:\n"
                "  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            ) from e

        if not os.path.isfile(client_secret_path):
            raise BackupError(f"Client secret file not found: {client_secret_path}")

        try:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        except Exception as e:
            raise BackupError(f"Google sign-in failed: {e}") from e

        self.token_path.write_text(creds.to_json())
        self.config.set("client_secret_path", client_secret_path)
        self.config.set("connect_mode", mode)

    def connect_quick(self):
        """Sign-in using the bundled, app-wide OAuth client — no file
        picker, nothing for the user to download. Raises BackupError if
        no one has set up the bundled client on this install yet."""
        if not self.is_bundled_client_available():
            raise BackupError(
                "Quick Connect isn't set up on this install yet — WealthMap needs a shared "
                "Google OAuth client bundled with it first. Use \"Advanced\" below in the "
                "meantime, or ask whoever administers WealthMap to add it."
            )
        self.connect(str(BUNDLED_CLIENT_SECRET_PATH), mode="quick")

    def disconnect(self):
        if self.token_path.exists():
            try:
                self.token_path.unlink()
            except Exception:
                pass
        self.config.set("folder_id", None)
        self._forget_stored_key()

    def _get_credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not self.token_path.exists():
            raise BackupError("Not connected to Google Drive yet.")
        creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json())
        return creds

    def _drive(self):
        from googleapiclient.discovery import build
        creds = self._get_credentials()
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def whoami(self) -> Optional[str]:
        """Best-effort email address of the connected Google account, for
        display in Settings. Returns None if not connected or the lookup
        fails for any reason (never raises)."""
        try:
            drive = self._drive()
            about = drive.about().get(fields="user").execute()
            return about.get("user", {}).get("emailAddress")
        except Exception:
            return None

    # ── Drive folder / file management ──────────────────────────────────

    def _ensure_backup_folder(self, drive) -> str:
        folder_id = self.config.get("folder_id")
        if folder_id:
            try:
                meta = drive.files().get(fileId=folder_id, fields="id,trashed").execute()
                if not meta.get("trashed"):
                    return folder_id
            except Exception:
                pass  # fall through and recreate/relocate

        query = (f"name = '{BACKUP_FOLDER_NAME}' and "
                 "mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        results = drive.files().list(q=query, fields="files(id,name)").execute()
        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            meta = {"name": BACKUP_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
            created = drive.files().create(body=meta, fields="id").execute()
            folder_id = created["id"]
        self.config.set("folder_id", folder_id)
        return folder_id

    def list_backups(self) -> List[Dict]:
        drive = self._drive()
        folder_id = self._ensure_backup_folder(drive)
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive.files().list(
            q=query, orderBy="createdTime desc",
            fields="files(id,name,createdTime,size)"
        ).execute()
        return results.get("files", [])

    def _prune_old_backups(self, drive, folder_id: str):
        retain = self.config.get("retain_count", DEFAULT_RETAIN)
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive.files().list(
            q=query, orderBy="createdTime desc", fields="files(id,name)"
        ).execute()
        files = results.get("files", [])
        for f in files[retain:]:
            try:
                drive.files().delete(fileId=f["id"]).execute()
            except Exception:
                pass

    # ── Archive creation / encryption ───────────────────────────────────

    def _build_archive(self) -> Path:
        """Zips profiles.json + profiles/ under the data root into a temp
        .zip file and returns its path. Caller is responsible for
        deleting it afterwards."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="wealthmap_backup_"))
        zip_path = tmp_dir / "data.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            registry_file = self.root / "profiles.json"
            if registry_file.exists():
                zf.write(registry_file, arcname="profiles.json")
            profiles_dir = self.root / "profiles"
            if profiles_dir.exists():
                for path in profiles_dir.rglob("*"):
                    if path.is_file():
                        zf.write(path, arcname=str(path.relative_to(self.root)))
        return zip_path

    def _encrypt_file(self, src_path: Path, key: bytes, salt: bytes) -> Path:
        """Writes salt(16 bytes) + Fernet token, so the salt needed to
        re-derive the key from a password travels *with* the archive
        itself — a salt isn't secret, only the password is, so this is
        what lets a backup be restored on a machine that has no local
        record of anything (a fresh PC)."""
        dst_path = src_path.with_suffix(".wmb")
        data = src_path.read_bytes()
        token = Fernet(key).encrypt(data)
        dst_path.write_bytes(salt + token)
        return dst_path

    def _decrypt_bytes(self, blob: bytes, password: str) -> bytes:
        salt, token = blob[:16], blob[16:]
        key = _derive_key(password, salt)
        try:
            return Fernet(key).decrypt(token)
        except InvalidToken as e:
            raise WrongPassword("That backup password is incorrect for this file.") from e

    # ── Backup ────────────────────────────────────────────────────────────

    def backup_now(self) -> Dict:
        """Runs a full backup synchronously using the currently-unlocked
        session key. Raises BackupError / WrongPassword on failure."""
        if not self.is_connected():
            raise BackupError("Not connected to Google Drive.")
        if not self.is_unlocked:
            raise BackupError("Backup password isn't unlocked for this session.")

        with self._lock:
            if self._running:
                return {"skipped": "already running"}
            self._running = True

        tmp_dir = None
        try:
            self._status("Creating backup archive…")
            zip_path = self._build_archive()
            tmp_dir = zip_path.parent
            salt = base64.b64decode(self.config.data["password_salt"])
            enc_path = self._encrypt_file(zip_path, self._session_key, salt)

            self._status("Connecting to Google Drive…")
            drive = self._drive()
            folder_id = self._ensure_backup_folder(drive)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"wealthmap_backup_{stamp}.wmb"

            self._status("Uploading…")
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(str(enc_path), mimetype="application/octet-stream", resumable=False)
            drive.files().create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media, fields="id"
            ).execute()

            self._prune_old_backups(drive, folder_id)

            now_iso = datetime.now(timezone.utc).isoformat()
            self.config.set("last_backup_at", now_iso)
            self.config.set("last_backup_error", None)
            self._status(f"Backup complete ({filename}).")
            return {"ok": True, "filename": filename, "at": now_iso}
        except Exception as e:
            self.config.set("last_backup_error", str(e))
            self._status(f"Backup failed: {e}")
            raise
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            with self._lock:
                self._running = False

    def backup_now_async(self, on_done: Optional[Callable[[Optional[Exception]], None]] = None):
        def run():
            err = None
            try:
                self.backup_now()
            except Exception as e:
                err = e
            if on_done:
                on_done(err)
        threading.Thread(target=run, daemon=True).start()

    # ── Triggers ─────────────────────────────────────────────────────────

    def mark_dirty(self):
        """Call after any data mutation. If the 'on_change' trigger is
        enabled, (re)starts a debounce timer so a burst of edits results
        in one backup a short while after things go quiet, not one per
        edit."""
        if "on_change" not in self.config.triggers:
            return
        if not (self.is_connected() and self.is_unlocked):
            return
        with self._lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(DEBOUNCE_SECONDS, self._debounced_fire)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _debounced_fire(self):
        self.backup_now_async()

    def maybe_daily_backup(self):
        if "daily" not in self.config.triggers:
            return
        if not (self.is_connected() and self.is_unlocked):
            return
        last = self.config.get("last_backup_at")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if age < DAILY_SECONDS:
                    return
            except Exception:
                pass
        self.backup_now_async()

    def backup_on_close_blocking(self, timeout: float = 8.0) -> bool:
        """Best-effort synchronous backup used when the app is closing —
        gives the upload a few seconds to finish but never blocks the
        close indefinitely. Returns True if it completed in time."""
        if "on_close" not in self.config.triggers:
            return True
        if not (self.is_connected() and self.is_unlocked):
            return True
        done = threading.Event()
        result = {}

        def run():
            try:
                self.backup_now()
            except Exception as e:
                result["error"] = e
            done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return done.wait(timeout)

    # ── Restore ──────────────────────────────────────────────────────────

    def download_backup(self, file_id: str, dest_path: Path):
        from googleapiclient.http import MediaIoBaseDownload
        import io
        drive = self._drive()
        request = drive.files().get_media(fileId=file_id)
        with io.FileIO(str(dest_path), "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def restore_from_file(self, encrypted_path: Path, password: str, backup_existing: bool = True):
        """Decrypts `encrypted_path` with `password` and extracts it over
        this data root. Works on a completely fresh PC with no prior
        WealthMap install, because the salt needed to check the password
        travels inside the backup archive itself (see `_encrypt_file`) —
        nothing local is required beforehand except the password the
        user chose when they first set up backups.

        If `backup_existing` is True, anything currently under the data
        root is first copied aside to `<root>_pre_restore_<timestamp>/`
        rather than being overwritten blindly, in case the restore needs
        to be undone."""
        raw = encrypted_path.read_bytes()
        data = self._decrypt_bytes(raw, password)  # raises WrongPassword if wrong

        if backup_existing and self.root.exists() and any(self.root.iterdir()):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            aside = self.root.parent / f"{self.root.name}_pre_restore_{stamp}"
            shutil.copytree(self.root, aside)

        tmp_dir = Path(tempfile.mkdtemp(prefix="wealthmap_restore_"))
        zip_path = tmp_dir / "data.zip"
        zip_path.write_bytes(data)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self.root)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # backup_config.json isn't part of the archive (only profiles.json
        # + profiles/ are backed up), so this machine's connection info
        # (folder_id, client_secret_path) is left as-is, and we register
        # the just-used password locally (fresh local salt/verifier) so
        # future automatic backups on this machine can check it without
        # re-deriving from an archive. set_password() also unlocks the
        # session key, which is what future backup_now() calls need (they
        # derive from the *local* salt going forward).
        self.set_password(password)
