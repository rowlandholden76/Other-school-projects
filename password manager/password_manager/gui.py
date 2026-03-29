import os
import tkinter as tk
import ctypes
import tkinter.font as tkfont
import datetime
from tkinter import messagebox, ttk
from typing import Optional

# milliseconds before clearing clipboard after copy
CLIPBOARD_CLEAR_MS = 15_000

from .storage import PasswordStore
from .config import get_config_value, set_config_value
from .crypto import generate_password
from .wincred import (
    get_credential,
    set_credential,
    get_credential_with_time,
    delete_credential,
    logger,
)
from .sync import reconcile_user_with_os
from .gui_oscred import modal_os_credentials_dialog


def datetime_from_iso(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)


class PasswordManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Password Manager")

        self.store = PasswordStore(path="vault.json")
        self.current_user: Optional[str] = None
        self.user_password: Optional[str] = None
        self._clipboard_job = None
        # load clipboard timeout from separate config file if available
        try:
            ms = get_config_value("clipboard_ms", None)
            if ms is not None:
                # allow older/hand-edited values in seconds (e.g. '30') or
                # milliseconds (e.g. '30000'). Treat small integers as seconds.
                val = int(ms)
                if val < 1000:
                    val = val * 1000
                self._clipboard_ms = val
            else:
                self._clipboard_ms = CLIPBOARD_CLEAR_MS
        except Exception:
            self._clipboard_ms = CLIPBOARD_CLEAR_MS

        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.left = ttk.Frame(self.main_frame)
        self.left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right = ttk.Frame(self.main_frame)
        self.right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        search_frame = ttk.Frame(self.left)
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_list())
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.listbox = tk.Listbox(self.left, height=20)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<Double-Button-1>", self.on_listbox_double)

        # menu bar
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Preferences", command=self.show_preferences)
        file_menu.add_command(label="Sync OS ↔ Vault", command=self.sync_with_os)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

        btn_frame = ttk.Frame(self.left)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Refresh", command=self.refresh_list).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Add", command=self.add_entry).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="View", command=self.view_entry).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Edit", command=self.edit_entry).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Copy", command=self.copy_password).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Delete", command=self.delete_entry).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Generate", command=self.show_generated).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Logout", command=self.logout).pack(side=tk.LEFT)

        self.detail_text = tk.Text(self.right, height=20, width=40)
        self.detail_text.pack(fill=tk.BOTH, expand=True)

        if not self.store.initialized():
            self.show_init()
        else:
            self.show_unlock()

    def show_init(self):
        # Initialize the store file and create the first user account
        res = modal_create_user_dialog(self.root)
        if not res:
            self.root.destroy()
            return
        username = res.get("username")
        pwd = res.get("password")
        save = bool(res.get("save"))
        if not username or not pwd:
            self.root.destroy()
            return
        try:
            # only initialize the on-disk store after the user confirmed
            try:
                self.store.init_store()
            except Exception:
                pass
            self.store.create_user(username, pwd)
            if save:
                try:
                    set_credential("PasswordManager", username, pwd)
                    try:
                        set_config_value("os_saved_username", username)
                    except Exception:
                        pass
                    try:
                        _, dt = get_credential_with_time("PasswordManager", username)
                        if dt is not None:
                            try:
                                self.store.set_os_credential_timestamp(username, dt.isoformat())
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    # ignore failures to set OS credential
                    pass
            messagebox.showinfo("Initialized", "Vault created at vault.json", parent=self.root)
            self.current_user = username
            self.user_password = pwd
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)
            self.root.destroy()

    def show_unlock(self):
        # attempt to auto-retrieve saved credential
        saved_user = None
        try:
            saved_user = get_config_value("os_saved_username", None)
        except Exception:
            saved_user = None
        if saved_user:
            try:
                saved_pwd = get_credential("PasswordManager", saved_user)
            except Exception:
                saved_pwd = None
            if saved_pwd:
                # try to authenticate
                os_pwd, os_dt = get_credential_with_time("PasswordManager", saved_user)
                # if keyring fallback returned only password, os_dt may be None
                if os_pwd:
                    try:
                        # try to authenticate using OS-saved password
                        self.store.authenticate_user(saved_user, os_pwd)
                        # read stored timestamp
                        try:
                            stored_iso = self.store.get_os_credential_timestamp(saved_user)
                        except Exception:
                            stored_iso = None
                        stored_dt = None
                        if stored_iso:
                            try:
                                stored_dt = datetime_from_iso(stored_iso)
                            except Exception:
                                stored_dt = None

                        # If OS timestamp is newer, update our stored timestamp.
                        # Normalize timestamps to second precision to avoid repeated syncs
                        if os_dt:
                            try:
                                os_dt_norm = os_dt.replace(microsecond=0)
                            except Exception:
                                os_dt_norm = os_dt
                            try:
                                if stored_dt is None:
                                    # store normalized ISO string
                                    self.store.set_os_credential_timestamp(saved_user, os_dt_norm.isoformat())
                                else:
                                    try:
                                        stored_dt_norm = stored_dt.replace(microsecond=0)
                                    except Exception:
                                        stored_dt_norm = stored_dt
                                    # Only update if different after normalization and OS is newer
                                    if os_dt_norm > stored_dt_norm and os_dt_norm != stored_dt_norm:
                                        try:
                                            self.store.set_os_credential_timestamp(saved_user, os_dt_norm.isoformat())
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                        # If stored timestamp is newer, offer to update OS credential from vault
                        if stored_dt and (os_dt is None or stored_dt > os_dt):
                            try:
                                do_update = messagebox.askyesno(
                                    "Sync credentials",
                                    "Vault credential appears newer than OS-saved credential.\nUpdate OS credential from the vault?",
                                    parent=self.root,
                                )
                                if do_update:
                                    # require the user to confirm their vault password before exporting
                                    pwd_confirm = modal_askstring(self.root, "Confirm password", "Enter your vault password to update OS credential:", show='*')
                                    if pwd_confirm:
                                        try:
                                            # verify provided password
                                            self.store.authenticate_user(saved_user, pwd_confirm)
                                            set_credential("PasswordManager", saved_user, pwd_confirm)
                                            # refresh timestamp (normalize to seconds)
                                            try:
                                                _, new_dt = get_credential_with_time("PasswordManager", saved_user)
                                                if new_dt is not None:
                                                    try:
                                                        new_dt_norm = new_dt.replace(microsecond=0)
                                                    except Exception:
                                                        new_dt_norm = new_dt
                                                    self.store.set_os_credential_timestamp(saved_user, new_dt_norm.isoformat())
                                            except Exception:
                                                pass
                                        except Exception:
                                            messagebox.showerror("Error", "Password verification failed; OS credential not updated.", parent=self.root)
                            except Exception:
                                pass

                        self.current_user = saved_user
                        self.user_password = os_pwd
                        # Inform the user that an automatic login occurred
                        try:
                            messagebox.showinfo("Auto-login", f"Automatically logged in as '{saved_user}' using the OS credential store.", parent=self.root)
                        except Exception:
                            pass
                        self.refresh_list()
                        return
                    except Exception:
                        # authentication failed; offer to re-encrypt the vault to match the OS-saved password
                        try:
                            do_reencrypt = messagebox.askyesno(
                                "Sync passwords",
                                "OS-saved credential does not match the vault.\n\nWould you like to update the vault to use the OS-saved password?\n(You will need to confirm your current vault password.)",
                                parent=self.root,
                            )
                            if do_reencrypt:
                                old_pwd = modal_askstring(self.root, "Confirm current password", "Enter your current vault password:", show='*')
                                if old_pwd:
                                    try:
                                        self.store.change_password(saved_user, old_pwd, os_pwd)
                                        # refresh stored timestamp for OS credential
                                        try:
                                            _, new_dt = get_credential_with_time("PasswordManager", saved_user)
                                            if new_dt is not None:
                                                try:
                                                    new_dt_norm = new_dt.replace(microsecond=0)
                                                except Exception:
                                                    new_dt_norm = new_dt
                                                self.store.set_os_credential_timestamp(saved_user, new_dt_norm.isoformat())
                                        except Exception:
                                            pass
                                        self.current_user = saved_user
                                        self.user_password = os_pwd
                                        self.refresh_list()
                                        return
                                    except Exception:
                                        messagebox.showerror("Error", "Failed to update vault password. Vault unchanged.", parent=self.root)
                        except Exception:
                            pass
        res = modal_login_dialog(self.root)
        if not res:
            self.root.destroy()
            return
        username = res.get("username")
        pwd = res.get("password")
        save = bool(res.get("save"))
        if not username or not pwd:
            self.root.destroy()
            return
        try:
            self.store.authenticate_user(username, pwd)
            self.current_user = username
            self.user_password = pwd
            if save:
                try:
                    set_credential("PasswordManager", username, pwd)
                    try:
                        set_config_value("os_saved_username", username)
                    except Exception:
                        pass
                    try:
                        _, dt = get_credential_with_time("PasswordManager", username)
                        if dt is not None:
                            try:
                                self.store.set_os_credential_timestamp(username, dt.isoformat())
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
            self.refresh_list()
        except Exception:
            messagebox.showerror("Error", "Invalid username or password", parent=self.root)
            self.root.destroy()

    def refresh_list(self):
        try:
            if not self.current_user:
                names = []
            else:
                names = self.store.list_entries(self.current_user)
        except Exception:
            names = []
        q = self.search_var.get().lower() if hasattr(self, "search_var") else ""
        # remember previously selected entry name so we can refresh details
        prev_sel = None
        try:
            sel = self.listbox.curselection()
            if sel:
                prev_sel = self.listbox.get(sel[0])
        except Exception:
            prev_sel = None

        self.listbox.delete(0, tk.END)
        for n in names:
            if q and q not in n.lower():
                continue
            self.listbox.insert(tk.END, n)

        # restore selection and refresh details pane if possible
        if prev_sel:
            try:
                items = [self.listbox.get(i) for i in range(self.listbox.size())]
                idx = items.index(prev_sel)
                self.listbox.selection_set(idx)
                self.view_entry()
            except ValueError:
                # previous selection no longer exists
                self.detail_text.delete("1.0", tk.END)

    def add_entry(self):
        if not self.user_password or not self.current_user:
            messagebox.showerror("Error", "Unlock the vault first", parent=self.root)
            return
        res = modal_add_entry_dialog(self.root)
        if not res:
            return
        name = res.get("name")
        username = res.get("username") or ""
        pwd = res.get("password") or ""
        if not name:
            return
        if not pwd:
            # generate if blank
            pwd = generate_password()
            messagebox.showinfo("Generated", f"Generated password: {pwd}", parent=self.root)
        try:
            source = {"type": "user", "name": "manual"}
            self.store.add_entry(self.current_user, name, username, pwd, self.user_password, source=source)
            messagebox.showinfo("Saved", f"Saved entry: {name}", parent=self.root)
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def view_entry(self):
        if not self.user_password or not self.current_user:
            messagebox.showerror("Error", "Unlock the vault first", parent=self.root)
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            assert self.current_user is not None and self.user_password is not None
            entry = self.store.get_entry(self.current_user, name, self.user_password)
            if not entry:
                messagebox.showinfo("Not found", "Entry not found", parent=self.root)
                return
            self.detail_text.delete("1.0", tk.END)
            self.detail_text.insert(tk.END, f"Name: {name}\n")
            self.detail_text.insert(tk.END, f"Username: {entry.get('username')}\n")
            self.detail_text.insert(tk.END, f"Password: {entry.get('password')}\n")
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def show_generated(self):
        pwd = generate_password()
        messagebox.showinfo("Generated", f"Generated password: {pwd}", parent=self.root)

    def logout(self):
        self.user_password = None
        self.current_user = None
        messagebox.showinfo("Logged out", "Vault locked", parent=self.root)
        self.root.destroy()

    def delete_entry(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        if not messagebox.askyesno("Delete", f"Delete entry '{name}'?", parent=self.root):
            return
        try:
            if not self.current_user:
                raise RuntimeError("Unlock the vault first")
            self.store.delete_entry(self.current_user, name)
            messagebox.showinfo("Deleted", f"Deleted: {name}", parent=self.root)
            self.refresh_list()
            self.detail_text.delete("1.0", tk.END)
        except KeyError:
            messagebox.showerror("Error", "Entry not found", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def copy_password(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            assert self.current_user is not None and self.user_password is not None
            entry = self.store.get_entry(self.current_user, name, self.user_password)
            if not entry:
                messagebox.showinfo("Not found", "Entry not found", parent=self.root)
                return
            pwd = entry.get("password") or ""
            self.root.clipboard_clear()
            self.root.clipboard_append(pwd)
            messagebox.showinfo("Copied", "Password copied to clipboard", parent=self.root)
            # schedule clipboard clear
            try:
                if self._clipboard_job:
                    self.root.after_cancel(self._clipboard_job)
            except Exception:
                pass
            self._clipboard_job = self.root.after(self._clipboard_ms, self._clear_clipboard)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def _clear_clipboard(self):
        try:
            self.root.clipboard_clear()
        except Exception:
            pass
        self._clipboard_job = None

    def on_listbox_double(self, event):
        # ensure the item under the pointer is selected, then view it
        idx = self.listbox.nearest(event.y)
        if idx is None:
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.view_entry()

    def show_preferences(self):
        # current value in seconds
        cur_ms = self._clipboard_ms
        cur_s = int(cur_ms / 1000)
        res = modal_pref_dialog(self.root, cur_s)
        if res is None:
            return
        try:
            val_s = int(res)
            if val_s < 0:
                raise ValueError()
            self._clipboard_ms = val_s * 1000
            try:
                set_config_value("clipboard_ms", self._clipboard_ms)
            except Exception:
                pass
        except ValueError:
            messagebox.showerror("Invalid", "Please enter a non-negative integer seconds value.", parent=self.root)

        # offer OS credentials management
        if messagebox.askyesno("OS Credentials", "Open OS credential manager settings?", parent=self.root):
            modal_os_credentials_dialog(self.root, self.store)

    def edit_entry(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            assert self.current_user is not None and self.user_password is not None
            entry = self.store.get_entry(self.current_user, name, self.user_password)
            if not entry:
                messagebox.showinfo("Not found", "Entry not found", parent=self.root)
                return
            res = modal_edit_entry(self.root, f"Edit: {name}", name, username=entry.get("username"), password=entry.get("password"))
            if not res:
                return
            self.store.add_entry(self.current_user, name, res.get("username", ""), res.get("password", ""), self.user_password)
            messagebox.showinfo("Saved", f"Updated entry: {name}", parent=self.root)
            self.refresh_list()
            self.view_entry()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)
    
    def sync_with_os(self):
        """Sync entries for the currently unlocked user with the OS credential store.

        Rules: for each entry (union of vault and OS entries) the newest wins based on per-entry OS timestamp tracked in the vault and the OS credential LastWritten time.
        """
        if not self.current_user or not self.user_password:
            messagebox.showerror("Error", "Unlock the vault first", parent=self.root)
            return
        try:
            summary = reconcile_user_with_os(self.store, self.current_user, self.user_password)
            messagebox.showinfo("Sync complete", "OS <-> Vault sync complete for current user.", parent=self.root)
        except Exception:
            messagebox.showerror("Error", "OS credential enumeration not available on this platform.", parent=self.root)
            return


def run_gui():
    # Set AppUserModelID before creating the Tk root so Windows taskbar uses our app id.
    myappid = "HoldenRowland.passwordmanager.1.0"
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        # Non-windows or not available; ignore silently
        pass

    root = tk.Tk()

    # Load icons using absolute paths relative to the package to avoid cwd issues
    icons_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "icons"))
    png_path = os.path.join(icons_dir, "icon.png")
    ico_path = os.path.join(icons_dir, "icon.ico")
    try:
        if os.path.exists(png_path):
            icon = tk.PhotoImage(file=png_path)
            root.iconphoto(True, icon)
    except Exception:
        pass
    try:
        if os.path.exists(ico_path):
            root.iconbitmap(ico_path)
    except Exception:
        pass

    app = PasswordManagerGUI(root)
    root.mainloop()


def modal_askstring(parent, title, prompt, show=None) -> Optional[str]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title(title)

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    lbl = ttk.Label(frm, text=prompt)
    lbl.pack(side=tk.TOP, anchor=tk.W)

    entry_var = tk.StringVar()
    entry = ttk.Entry(frm, textvariable=entry_var, show=(show or ""))
    entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(5, 10))
    entry.focus_set()

    result: dict[str, Optional[str]] = {"value": None}

    def on_ok(event=None):
        result["value"] = entry_var.get()
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X)
    ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok)
    ok_btn.pack(side=tk.LEFT)
    cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
    cancel_btn.pack(side=tk.LEFT)

    entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center over parent window
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]


def modal_edit_entry(parent, title, name, username: Optional[str] = "", password: Optional[str] = "") -> Optional[dict]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title(title)

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text=f"Name: {name}").pack(side=tk.TOP, anchor=tk.W)

    ttk.Label(frm, text="Username:").pack(side=tk.TOP, anchor=tk.W, pady=(6, 0))
    user_var = tk.StringVar(value=username or "")
    user_entry = ttk.Entry(frm, textvariable=user_var)
    user_entry.pack(side=tk.TOP, fill=tk.X, expand=True)

    ttk.Label(frm, text="Password:").pack(side=tk.TOP, anchor=tk.W, pady=(6, 0))
    pwd_var = tk.StringVar(value=password or "")
    pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*')
    pwd_entry.pack(side=tk.TOP, fill=tk.X, expand=True)

    result: dict[str, Optional[dict]] = {"value": None}

    def on_ok(event=None):
        result["value"] = {"username": user_var.get(), "password": pwd_var.get()}
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    user_entry.focus_set()
    user_entry.bind("<Return>", lambda e: pwd_entry.focus_set())
    pwd_entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center dialog over parent
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]


def modal_login_dialog(parent) -> Optional[dict]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title("Login")

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Username:").pack(side=tk.TOP, anchor=tk.W)
    user_var = tk.StringVar()
    user_entry = ttk.Entry(frm, textvariable=user_var)
    user_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 8))

    ttk.Label(frm, text="Password:").pack(side=tk.TOP, anchor=tk.W)
    pwd_var = tk.StringVar()
    pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*')
    pwd_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 6))

    # small note on case-sensitivity
    try:
        small_font = tkfont.Font(size=7)
    except Exception:
        small_font = None
    note = ttk.Label(frm, text="Usernames are case-sensitive.")
    if small_font is not None:
        note.configure(font=small_font)
    note.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    save_var = tk.BooleanVar(value=False)
    cb = ttk.Checkbutton(frm, text="Save login to OS credential store", variable=save_var)
    cb.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    result: dict[str, Optional[dict]] = {"value": None}

    def on_ok(event=None):
        result["value"] = {"username": user_var.get(), "password": pwd_var.get(), "save": save_var.get()}
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    user_entry.focus_set()
    user_entry.bind("<Return>", lambda e: pwd_entry.focus_set())
    pwd_entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center dialog over parent
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]


def modal_create_user_dialog(parent) -> Optional[dict]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title("Create user")

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Create username:").pack(side=tk.TOP, anchor=tk.W)
    user_var = tk.StringVar()
    user_entry = ttk.Entry(frm, textvariable=user_var)
    user_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 8))

    ttk.Label(frm, text="Create password:").pack(side=tk.TOP, anchor=tk.W)
    pwd_var = tk.StringVar()
    pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*')
    pwd_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 6))

    ttk.Label(frm, text="Confirm password:").pack(side=tk.TOP, anchor=tk.W)
    confirm_var = tk.StringVar()
    confirm_entry = ttk.Entry(frm, textvariable=confirm_var, show='*')
    confirm_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 6))

    # small note on case-sensitivity
    try:
        small_font = tkfont.Font(size=7)
    except Exception:
        small_font = None
    note = ttk.Label(frm, text="Usernames are case-sensitive.")
    if small_font is not None:
        note.configure(font=small_font)
    note.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    save_var = tk.BooleanVar(value=False)
    cb = ttk.Checkbutton(frm, text="Save login to OS credential store", variable=save_var)
    cb.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    result: dict[str, Optional[dict]] = {"value": None}

    def on_ok(event=None):
        u = user_var.get()
        p = pwd_var.get()
        c = confirm_var.get()
        if p != c:
            messagebox.showerror("Error", "Passwords do not match", parent=dlg)
            return
        result["value"] = {"username": u, "password": p, "save": save_var.get()}
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    user_entry.focus_set()
    user_entry.bind("<Return>", lambda e: pwd_entry.focus_set())
    pwd_entry.bind("<Return>", lambda e: confirm_entry.focus_set())
    confirm_entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center dialog over parent
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]


def modal_add_entry_dialog(parent) -> Optional[dict[str, str]]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title("Add entry")

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Name:").pack(side=tk.TOP, anchor=tk.W)
    name_var = tk.StringVar()
    name_entry = ttk.Entry(frm, textvariable=name_var)
    name_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 8))

    ttk.Label(frm, text="Username:").pack(side=tk.TOP, anchor=tk.W)
    user_var = tk.StringVar()
    user_entry = ttk.Entry(frm, textvariable=user_var)
    user_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 8))

    ttk.Label(frm, text="Password (leave blank to generate):").pack(side=tk.TOP, anchor=tk.W)
    pwd_var = tk.StringVar()
    pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*')
    pwd_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 6))

    ttk.Label(frm, text="Confirm password:").pack(side=tk.TOP, anchor=tk.W)
    confirm_var = tk.StringVar()
    confirm_entry = ttk.Entry(frm, textvariable=confirm_var, show='*')
    confirm_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 6))

    # short helper text
    try:
        small_font = tkfont.Font(size=9)
    except Exception:
        small_font = None
    help_lbl = ttk.Label(frm, text="If password left blank a random password will be generated.")
    if small_font is not None:
        help_lbl.configure(font=small_font)
    help_lbl.pack(side=tk.TOP, anchor=tk.W, pady=(4, 8))

    result: dict[str, Optional[dict[str, str]]] = {"value": None}

    def on_ok(event=None):
        name = name_var.get().strip()
        pwd = pwd_var.get()
        conf = confirm_var.get()
        # if password provided, confirm required
        if pwd:
            if conf != pwd:
                messagebox.showerror("Error", "Passwords do not match", parent=dlg)
                return
        result["value"] = {"name": name, "username": user_var.get(), "password": pwd}
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    name_entry.focus_set()
    name_entry.bind("<Return>", lambda e: user_entry.focus_set())
    user_entry.bind("<Return>", lambda e: pwd_entry.focus_set())
    pwd_entry.bind("<Return>", lambda e: confirm_entry.focus_set())
    confirm_entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center dialog
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]


def modal_pref_dialog(parent, current_seconds: int) -> Optional[str]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title("Preferences")

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Clipboard clear timeout (seconds):").pack(side=tk.TOP, anchor=tk.W)
    sec_var = tk.StringVar(value=str(current_seconds))
    sec_entry = ttk.Entry(frm, textvariable=sec_var)
    sec_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(5, 10))
    sec_entry.focus_set()

    # brief note about username behavior
    ttk.Label(frm, text="Note: Usernames are case-sensitive.").pack(side=tk.TOP, anchor=tk.W, pady=(4, 6))

    result: dict[str, Optional[str]] = {"value": None}

    def on_ok(event=None):
        result["value"] = sec_var.get()
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    def on_cancel(event=None):
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    sec_entry.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    # center dialog
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        dlg.geometry(f"+{x}+{y}")
    except Exception:
        pass

    dlg.wait_window()
    return result["value"]
