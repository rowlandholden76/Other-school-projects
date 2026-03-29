# Password Manager — Usage

Install dependencies and run from the project root:

```powershell
python -m pip install -r requirements.txt
python main.py <command>
```

Commands:
- `init` — Initialize a vault (`vault.json`). The tool will prompt to create the first user account (username + password).
- `add` — Add an entry. Options: `--name`, `--username`, `--password`, `--generate`, and `--owner` to specify which user account to add into. When using the CLI you must specify the account to use (or be authenticated); the GUI will handle this for you.
- `get <name>` — Retrieve and print the username/password for the named entry (for the current user). Use `--owner` to read entries for a specific user when using the CLI.
- `gui` — Launch the Tkinter GUI for managing the vault.

GUI notes:

- Run `python main.py gui` to start the GUI. The GUI now uses per-user accounts — unlock by entering your username and password. Usernames are case-sensitive.
- On initial run `init` (or the GUI) you will be prompted to create the first user account. The vault stores entries per username so different accounts have separate entry sets.
- When creating or logging in the GUI you may opt to "Save login to OS credential store". If enabled the app will store the username/password in the OS credential manager (Windows Credential Manager on Windows, or the `keyring` backend on other platforms). The GUI will attempt to auto-retrieve the OS-saved credential on startup and will reconcile timestamps so the most recently written source (OS credential or vault metadata) wins.
- Use File → Preferences to change the clipboard auto-clear timeout (seconds). Preferences are saved to `config.json` in the project root.

  The `clipboard_ms` value in `config.json` may be written as milliseconds (e.g. `30000`) or as a small integer treated as seconds (e.g. `30`). The GUI will accept either format.

- Testing clipboard behavior

- A helper script `scripts/test_clipboard.py` is provided to copy the `UKG` entry (or change the constants at the top of the script) to the clipboard and verify that it is cleared after the configured timeout.

Run:

```powershell
python scripts/test_clipboard.py
```

- Double-click an entry to view details; use Copy to copy the password (clipboard clears automatically).

Notes:
- The vault is stored as JSON in `vault.json` by default. The on-disk format now supports multiple users under a top-level `users` mapping. Each user object contains `salt`, `verifier`, and `entries` (encrypted tokens).
- Each stored entry payload contains `username`, `password`, and optional `source` metadata. `source` is a small JSON object describing provenance, e.g. `{ "type": "user", "name": "manual" }` or `{ "type": "os", "name": "windows-credential-manager" }`.
- The GUI offers an opt-in to save credentials to the OS credential store. When used on Windows the app will use the Windows Credential Manager and will track the credential LastWritten time to help reconcile updates across devices.
- A helper migration script is provided to move legacy single-user vaults into the per-user schema. To migrate an existing `vault.json` into a per-user vault and back it up, run:

```powershell
python scripts/migrate_vault.py
```

The script creates a `vault.json.bak` backup and migrates existing entries under the username `Rowland` by default (edit the script if you want a different target).
- Preferences are stored in `config.json` in the project root.
- Backwards compatibility: the code still supports a legacy single-master workflow by writing into a hidden `_default` user for tools that expect a single master password.
- Use a secure password for your account and keep backups as needed.
