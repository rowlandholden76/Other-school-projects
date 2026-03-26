# Password Manager

Lightweight local password manager using encrypted vault.

Features

- Add and retrieve login credentials
- Master password authentication
- Local encrypted file storage (vault.json)
- Optional auto-generate strong passwords

Quick start

1. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Initialize the vault (one-time):

```powershell
python main.py init
```

3. Add an entry (CLI):

```powershell
python main.py add --name example.com --username alice
```

4. Retrieve an entry (CLI):

```powershell
python main.py get example.com
```

GUI

```powershell
python main.py gui
```

The GUI provides an interface to unlock the vault, add/edit/delete entries, copy passwords to the clipboard (auto-clears), and change preferences via File → Preferences.

Clipboard preference and test script

- Clipboard auto-clear timeout can be set via File → Preferences in the GUI. The value is stored in `config.json` as `clipboard_ms` and may be either milliseconds (e.g. `30000`) or a small integer treated as seconds (e.g. `30`).
- A small helper script `scripts/test_clipboard.py` is included to exercise copying an entry to the clipboard and verify the configured timeout.

Packaging and icons

- Icon assets live in `assets/icons/`. Use `scripts/generate_icons.py` to convert SVGs to PNG/ICO (requires `cairosvg` and `Pillow`).
- Build a Windows executable with the included helper:

```powershell
python scripts/generate_icons.py assets/icons/app.svg assets/icons/app.ico
python scripts/build_exe.py --onefile --windowed
```

This produces a single-file executable (PyInstaller) using `assets/icons/app.ico` as the application icon.

Files

- `main.py` — CLI entrypoint
- `password_manager/crypto.py` — key derivation & encrypt/decrypt
- `password_manager/storage.py` — vault file management
- `vault.json` — created after initialization
