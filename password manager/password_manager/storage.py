import base64
import json
import os
import datetime
from typing import Optional, Any, Dict, cast

from .crypto import generate_salt, derive_key, encrypt_bytes, decrypt_bytes
import logging

logger = logging.getLogger(__name__)


class PasswordStore:
    """Simple JSON-backed store supporting multiple users.

    File format:
    {
      "users": {
         "alice": {
             "salt": "base64...",
             "verifier": "base64...",
             "entries": { "gmail": "base64-token" }
         }
      }
    }
    """

    def __init__(self, path: str = "vault.json") -> None:
        self.path = path
        self._data: Optional[Dict[str, Any]] = None
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                # cast so type checkers treat loaded JSON as a dict of Any
                self._data = cast(Dict[str, Any], json.load(f))

    def initialized(self) -> bool:
        return self._data is not None

    def init_store(self) -> None:
        # initialize empty structure
        self._data = {"users": {}}
        self._write()

    def _write(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def create_user(self, username: str, password: str) -> None:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        if username in self._data.get("users", {}):
            raise KeyError("User already exists")
        salt = generate_salt()
        key = derive_key(password, salt)
        # store a verifier token encrypted with the derived key; successful decryption
        # proves the password without storing it in plaintext
        verifier = encrypt_bytes(b"verify", key)
        self._data["users"][username] = {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(verifier).decode(),
            "entries": {},
        }
        self._write()

    def authenticate_user(self, username: str, password: str) -> bytes:
        """Return derived key if authentication succeeds, else raise."""
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        meta = users[username]
        salt = base64.b64decode(meta["salt"])
        key = derive_key(password, salt)
        verifier = base64.b64decode(meta["verifier"])
        try:
            payload = decrypt_bytes(verifier, key)
            if payload != b"verify":
                raise ValueError("Invalid credentials")
        except Exception:
            raise ValueError("Invalid credentials")
        return key

    def add_entry(self, owner: str, name: str, entry_username: str, entry_password: str, user_password: str, source: Optional[Dict[str, Any]] = None) -> None:
        """Add or update an entry for a specific owner.

        The entry payload stores `username`, `password`, and optional `source` metadata.
        """
        if not self._data:
            raise RuntimeError("Vault not initialized")
        key = self.authenticate_user(owner, user_password)
        payload: Dict[str, Any] = {"username": entry_username, "password": entry_password}
        if source is not None:
            payload["source"] = source
        token = encrypt_bytes(json.dumps(payload).encode(), key)
        self._data["users"].setdefault(owner, {"salt": "", "verifier": "", "entries": {}})
        self._data["users"][owner].setdefault("entries", {})
        self._data["users"][owner]["entries"][name] = base64.b64encode(token).decode()
        self._write()

    def get_entry(self, owner: str, name: str, user_password: str) -> Optional[Dict[str, Any]]:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if owner not in users:
            raise KeyError("User not found")
        entries = users[owner].get("entries", {})
        if name not in entries:
            return None
        key = self.authenticate_user(owner, user_password)
        token = base64.b64decode(entries[name])
        payload = decrypt_bytes(token, key)
        return json.loads(payload.decode())

    def list_entries(self, owner: str) -> list:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if owner not in users:
            raise KeyError("User not found")
        return list(users[owner].get("entries", {}).keys())

    def list_users(self) -> list:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        return list(self._data.get("users", {}).keys())

    def get_entry_os_timestamp(self, username: str, name: str) -> Optional[str]:
        """Return the tracked OS LastWritten ISO timestamp for a specific entry."""
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        meta = users[username]
        em = meta.get("entries_meta", {})
        ent = em.get(name, {})
        return ent.get("os_last_written")

    def set_entry_os_timestamp(self, username: str, name: str, iso_ts: Optional[str]) -> None:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        meta = users[username]
        em = meta.setdefault("entries_meta", {})
        ent = em.setdefault(name, {})
        if iso_ts is None:
            ent.pop("os_last_written", None)
        else:
            ent["os_last_written"] = iso_ts
        try:
            self._write()
        except Exception:
            logger.exception("Failed to write vault when setting entry OS timestamp for %s/%s", username, name)

    def delete_entry(self, owner: str, name: str) -> None:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if owner not in users:
            raise KeyError("User not found")
        entries = users[owner].get("entries", {})
        if name in entries:
            del entries[name]
            self._write()
        else:
            raise KeyError(f"Entry not found: {name}")

    def get_os_credential_timestamp(self, username: str) -> Optional[str]:
        """Return ISO timestamp string of when the OS credential was last written (if tracked)."""
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        meta = users[username]
        m = meta.get("meta", {})
        return m.get("os_last_written")

    def set_os_credential_timestamp(self, username: str, iso_ts: Optional[str]) -> None:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        meta = users[username]
        mm = meta.setdefault("meta", {})
        # Allow clearing the stored timestamp by passing None
        if iso_ts is None:
            mm.pop("os_last_written", None)
        else:
            mm["os_last_written"] = iso_ts
        try:
            self._write()
        except Exception:
            logger.exception("Failed to write vault when setting OS timestamp for %s", username)

    def change_password(self, username: str, old_password: str, new_password: str) -> None:
        """Change the user's password, re-encrypting all entries with a new key/salt.

        Verifies the old password, then generates a new salt and re-encrypts entries.
        """
        if not self._data:
            raise RuntimeError("Vault not initialized")
        users = self._data.get("users", {})
        if username not in users:
            raise KeyError("User not found")
        # verify old password and obtain key
        old_key = self.authenticate_user(username, old_password)
        user_meta = users[username]
        entries = user_meta.get("entries", {})

        # decrypt all entries
        decrypted = {}
        for name, token_b64 in entries.items():
            token = base64.b64decode(token_b64)
            payload = decrypt_bytes(token, old_key)
            decrypted[name] = json.loads(payload.decode())

        # create new salt/key and verifier
        new_salt = generate_salt()
        new_key = derive_key(new_password, new_salt)
        new_verifier = encrypt_bytes(b"verify", new_key)

        # re-encrypt entries with new key
        new_entries = {}
        for name, payload in decrypted.items():
            token = encrypt_bytes(json.dumps(payload).encode(), new_key)
            new_entries[name] = base64.b64encode(token).decode()

        # update metadata
        user_meta["salt"] = base64.b64encode(new_salt).decode()
        user_meta["verifier"] = base64.b64encode(new_verifier).decode()
        user_meta["entries"] = new_entries
        try:
            self._write()
        except Exception:
            logger.exception("Failed to write vault when changing password for %s", username)
            raise
