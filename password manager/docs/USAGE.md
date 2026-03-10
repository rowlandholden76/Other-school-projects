# Password Manager — Usage

Install dependencies and run from the project root:

```powershell
python -m pip install -r requirements.txt
python main.py <command>
```

Commands:
- `init` — Initialize a vault (`vault.json`) and create a master password.
- `add` — Add an entry. Options: `--name`, `--username`, `--password`, `--generate`.
- `get <name>` — Retrieve and print the username/password for the named entry.
- `gui` — Launch the Tkinter GUI for managing the vault.

GUI notes:
- Run `python main.py gui` to start the GUI. Unlock with your master password.
- Use File → Preferences to change the clipboard auto-clear timeout (seconds). Preferences are saved to `config.json` in the project root.
	- The `clipboard_ms` value in `config.json` may be written as milliseconds (e.g. `30000`) or as a small integer treated as seconds (e.g. `30`). The GUI will accept either format.

Testing clipboard behavior
- A helper script `scripts/test_clipboard.py` is provided to copy the `UKG` entry (or change the constants at the top of the script) to the clipboard and verify that it is cleared after the configured timeout.
- Run:

```powershell
python scripts/test_clipboard.py
```
- Double-click an entry to view details; use Copy to copy the password (clipboard clears automatically).

Notes:
- The vault is stored as JSON in `vault.json` by default.
- Preferences are stored in `config.json` in the project root.
- Use a secure master password and keep backups as needed.
