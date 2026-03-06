import argparse
import getpass
import sys

from password_manager.crypto import generate_password
from password_manager.storage import PasswordStore


def main():
    parser = argparse.ArgumentParser(prog="password-manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init")

    addp = sub.add_parser("add")
    addp.add_argument("--name", required=False)
    addp.add_argument("--username", required=False)
    addp.add_argument("--password", required=False)
    addp.add_argument("--generate", action="store_true")

    getp = sub.add_parser("get")
    getp.add_argument("name")

    args = parser.parse_args()
    store = PasswordStore(path="vault.json")

    if args.cmd == "init":
        if store.initialized():
            print("Vault already initialized at vault.json")
            return
        master = getpass.getpass("Create master password: ")
        confirm = getpass.getpass("Confirm master password: ")
        if master != confirm:
            print("Master passwords do not match")
            return
        store.init_store(master)
        print("Initialized vault at vault.json")

    elif args.cmd == "add":
        if not store.initialized():
            print("Vault not initialized. Run: python main.py init")
            return
        name = args.name or input("Name: ")
        username = args.username or input("Username: ")
        if args.generate:
            password = generate_password()
            print("Generated password:", password)
        else:
            password = args.password or getpass.getpass("Password: ")
        master = getpass.getpass("Master password: ")
        try:
            store.add_entry(name, username, password, master)
            print("Saved entry:", name)
        except Exception as e:
            print("Error saving entry:", e)

    elif args.cmd == "get":
        if not store.initialized():
            print("Vault not initialized. Run: python main.py init")
            return
        master = getpass.getpass("Master password: ")
        entry = store.get_entry(args.name, master)
        if not entry:
            print("Entry not found")
            return
        print("Username:", entry.get("username"))
        print("Password:", entry.get("password"))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
