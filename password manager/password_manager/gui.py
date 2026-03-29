import os
import tkinter as tk
import ctypes
from tkinter import messagebox, ttk
from typing import Optional

# milliseconds before clearing clipboard after copy
CLIPBOARD_CLEAR_MS = 15_000

from .storage import PasswordStore
from .config import get_config_value, set_config_value
from .crypto import generate_password


class PasswordManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Password Manager")

        self.store = PasswordStore(path="vault.json")
        self.master_password: Optional[str] = None
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
        pwd = modal_askstring(self.root, "Create master", "Create master password:", show="*")
        if not pwd:
            self.root.destroy()
            return
        confirm = modal_askstring(self.root, "Confirm", "Confirm master password:", show="*")
        if pwd != confirm:
            messagebox.showerror("Error", "Master passwords do not match", parent=self.root)
            self.root.destroy()
            return
        self.store.init_store(pwd)
        messagebox.showinfo("Initialized", "Vault created at vault.json", parent=self.root)
        self.master_password = pwd
        self.refresh_list()

    def show_unlock(self):
        pwd = modal_askstring(self.root, "Unlock", "Master password:", show="*")
        if not pwd:
            self.root.destroy()
            return
        # If there are entries, try to decrypt first to validate; otherwise accept
        try:
            entries = self.store.list_entries()
            if entries:
                # attempt to get first entry to validate password
                first = entries[0]
                self.store.get_entry(first, pwd)
            self.master_password = pwd
            self.refresh_list()
        except Exception:
            messagebox.showerror("Error", "Invalid master password", parent=self.root)
            self.root.destroy()

    def refresh_list(self):
        try:
            names = self.store.list_entries()
        except Exception:
            names = []
        q = self.search_var.get().lower() if hasattr(self, "search_var") else ""
        self.listbox.delete(0, tk.END)
        for n in names:
            if q and q not in n.lower():
                continue
            self.listbox.insert(tk.END, n)

    def add_entry(self):
        if not self.master_password:
            messagebox.showerror("Error", "Unlock the vault first", parent=self.root)
            return
        name = modal_askstring(self.root, "Name", "Entry name:")
        if not name:
            return
        username = modal_askstring(self.root, "Username", "Username:") or ""
        pwd = modal_askstring(self.root, "Password", "Password (leave blank to generate):", show="*")
        if not pwd:
            pwd = generate_password()
            messagebox.showinfo("Generated", f"Generated password: {pwd}", parent=self.root)
        try:
            self.store.add_entry(name, username, pwd, self.master_password)
            messagebox.showinfo("Saved", f"Saved entry: {name}", parent=self.root)
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)

    def view_entry(self):
        if not self.master_password:
            messagebox.showerror("Error", "Unlock the vault first", parent=self.root)
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            entry = self.store.get_entry(name, self.master_password)
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
        self.master_password = None
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
            self.store.delete_entry(name)
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
            entry = self.store.get_entry(name, self.master_password)
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

    def edit_entry(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        try:
            entry = self.store.get_entry(name, self.master_password)
            if not entry:
                messagebox.showinfo("Not found", "Entry not found", parent=self.root)
                return
            res = modal_edit_entry(self.root, f"Edit: {name}", name, username=entry.get("username"), password=entry.get("password"))
            if not res:
                return
            self.store.add_entry(name, res.get("username", ""), res.get("password", ""), self.master_password)
            messagebox.showinfo("Saved", f"Updated entry: {name}", parent=self.root)
            self.refresh_list()
            self.view_entry()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)


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
