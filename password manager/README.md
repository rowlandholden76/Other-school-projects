# Password Manager

Lightweight local password manager using encrypted vault.

Features

- Add and retrieve login credentials
- Master password authentication
- Local encrypted file storage (vault.json)
- Optional auto-generate strong passwords

Quick start

1. Install dependencies:

```
pip install -r requirements.txt
```

2. Initialize the vault:

```
python main.py init
```

3. Add an entry:

```
python main.py add --name example.com --username alice
```

4. Retrieve an entry:

```
python main.py get example.com
```

Files

- `main.py` — CLI entrypoint
- `password_manager/crypto.py` — key derivation & encrypt/decrypt
- `password_manager/storage.py` — vault file management
- `vault.json` — created after initialization
