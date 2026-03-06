import base64
import json
import os
from typing import Optional

from .crypto import generate_salt, derive_key, encrypt_bytes, decrypt_bytes


class PasswordStore:
    def __init__(self, path: str = "vault.json") -> None:
        self.path = path
        self._data = None
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def initialized(self) -> bool:
        return self._data is not None

    def init_store(self, master_password: str) -> None:
        salt = generate_salt()
        self._data = {"salt": base64.b64encode(salt).decode(), "entries": {}}
        self._write()

    def _write(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def add_entry(self, name: str, username: str, password: str, master_password: str) -> None:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        salt = base64.b64decode(self._data["salt"])
        key = derive_key(master_password, salt)
        payload = json.dumps({"username": username, "password": password}).encode()
        token = encrypt_bytes(payload, key)
        self._data["entries"][name] = base64.b64encode(token).decode()
        self._write()

    def get_entry(self, name: str, master_password: str) -> Optional[dict]:
        if not self._data:
            raise RuntimeError("Vault not initialized")
        entries = self._data.get("entries", {})
        if name not in entries:
            return None
        salt = base64.b64decode(self._data["salt"])
        key = derive_key(master_password, salt)
        token = base64.b64decode(entries[name])
        payload = decrypt_bytes(token, key)
        return json.loads(payload.decode())
