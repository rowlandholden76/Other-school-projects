# Password Manager — API

Module: `password_manager.crypto`
- `generate_salt() -> bytes` — Generate a 16-byte random salt.
- `derive_key(password: str, salt: bytes) -> bytes` — Derive a 32-byte key (base64-urlsafe) using PBKDF2-HMAC-SHA256.
- `encrypt_bytes(data: bytes, key: bytes) -> bytes` — Encrypt bytes using Fernet.
- `decrypt_bytes(token: bytes, key: bytes) -> bytes` — Decrypt a Fernet token.
- `generate_password(length: int = 16) -> str` — Generate a secure random password.

Module: `password_manager.storage`
- `PasswordStore(path: str = "vault.json")` — Manage a JSON-backed password vault supporting multiple users.
  - `initialized() -> bool` — Vault loaded/initialized check.
  - `init_store()` — Create a new vault file (writes top-level `users` mapping).
  - `create_user(username: str, password: str)` — Create a new per-user account (generates salt and verifier).
  - `authenticate_user(username: str, password: str) -> bytes` — Authenticate and return the derived key (raises on failure).
  - `add_entry(owner: str, name: str, username: str, password: str, user_password: str, source: Optional[dict] = None)` — (per-user) Encrypt and store an entry for `owner` using `user_password` to derive the encryption key. The optional `source` dict records provenance (see notes).
  - `get_entry(owner: str, name: str, user_password: str) -> Optional[dict]` — (per-user) Decrypt and return the entry for `owner` (or `None`).
  - `list_entries(owner: str) -> list` — Return the entry names for the specified user.
  - `delete_entry(owner: str, name: str) -> None` — Remove an entry for the specified owner.
  - `get_os_credential_timestamp(username: str) -> Optional[str]` — Return an ISO timestamp (string) the store tracks for when the OS credential was last written for `username` (or `None`).
  - `set_os_credential_timestamp(username: str, iso_ts: Optional[str]) -> None` — Record or clear the tracked OS credential write timestamp for a user.
  - `change_password(username: str, old_password: str, new_password: str) -> None` — Re-encrypt all entries for `username` under a new password (creates a new salt and verifier).

Module: `password_manager.config`
- `get_config_value(key, default=None, path='config.json')` — Read a preference value from `config.json`.
- `set_config_value(key, value, path='config.json')` — Persist a preference value to `config.json`.

Module: `password_manager.gui`
- `run_gui()` — Launch the Tkinter-based GUI. Supports unlock, add/edit/delete, copy password (auto-clear), preferences, and per-user login.
- The GUI supports opting in to save the login to the OS credential store. When opted-in the app will attempt to auto-retrieve the credential on startup and reconcile the OS credential vs vault metadata timestamp to prefer the most recently written source.

CLI (`main.py`): `init`, `add`, `get` — see `USAGE.md` for examples.
