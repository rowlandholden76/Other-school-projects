# Password Manager — API

Module: `password_manager.crypto`
- `generate_salt() -> bytes` — Generate a 16-byte random salt.
- `derive_key(password: str, salt: bytes) -> bytes` — Derive a 32-byte key (base64-urlsafe) using PBKDF2-HMAC-SHA256.
- `encrypt_bytes(data: bytes, key: bytes) -> bytes` — Encrypt bytes using Fernet.
- `decrypt_bytes(token: bytes, key: bytes) -> bytes` — Decrypt a Fernet token.
- `generate_password(length: int = 16) -> str` — Generate a secure random password.

Module: `password_manager.storage`
- `PasswordStore(path: str = "vault.json")` — Manage a JSON-backed password vault.
  - `initialized() -> bool` — Vault loaded/initialized check.
  - `init_store(master_password: str)` — Create a new vault (writes salt and empty entries).
  - `add_entry(name, username, password, master_password)` — Encrypt and store an entry.
  - `get_entry(name, master_password) -> Optional[dict]` — Decrypt and return the entry (or `None`).
  - `list_entries() -> list` — Return a list of stored entry names.
  - `delete_entry(name)` — Remove an entry from the vault and write changes.

Module: `password_manager.config`
- `get_config_value(key, default=None, path='config.json')` — Read a preference value from `config.json`.
- `set_config_value(key, value, path='config.json')` — Persist a preference value to `config.json`.

Module: `password_manager.gui`
- `run_gui()` — Launch the Tkinter-based GUI. Supports unlock, add/edit/delete, copy password (auto-clear), and preferences.

CLI (`main.py`): `init`, `add`, `get` — see `USAGE.md` for examples.
