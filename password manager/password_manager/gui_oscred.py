import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional
import datetime

from .wincred import get_credential_with_time, delete_credential


def modal_os_credentials_dialog(parent, store) -> Optional[None]:
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.title("OS Credential Settings")

    frm = ttk.Frame(dlg, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Saved OS username:").pack(side=tk.TOP, anchor=tk.W)
    try:
        saved_user = None
        from .config import get_config_value
        saved_user = get_config_value("os_saved_username", None)
    except Exception:
        saved_user = None
    user_lbl = ttk.Label(frm, text=str(saved_user or "(none)"))
    user_lbl.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    ttk.Label(frm, text="OS LastWritten:").pack(side=tk.TOP, anchor=tk.W)
    os_lbl = ttk.Label(frm, text="(unknown)")
    os_lbl.pack(side=tk.TOP, anchor=tk.W, pady=(2, 8))

    ttk.Label(frm, text="Vault stored OS timestamp: (ISO)").pack(side=tk.TOP, anchor=tk.W)
    ts_var = tk.StringVar()
    ts_entry = ttk.Entry(frm, textvariable=ts_var)
    ts_entry.pack(side=tk.TOP, fill=tk.X, expand=True, pady=(2, 8))

    def refresh():
        if not saved_user:
            os_lbl.config(text="(none)")
            ts_var.set("")
            return
        try:
            pwd, dt = get_credential_with_time("PasswordManager", saved_user)
            os_lbl.config(text=str(dt) if dt else "(unknown)")
        except Exception:
            os_lbl.config(text="(error)")
        try:
            s = store.get_os_credential_timestamp(saved_user)
            ts_var.set(s or "")
        except Exception:
            ts_var.set("")

    def on_remove():
        if not saved_user:
            return
        if not messagebox.askyesno("Remove", f"Remove OS saved login for '{saved_user}'?", parent=dlg):
            return
        try:
            delete_credential("PasswordManager", saved_user)
            try:
                from .config import set_config_value
                set_config_value("os_saved_username", None)
            except Exception:
                pass
            messagebox.showinfo("Removed", "OS saved login removed", parent=dlg)
            refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=dlg)

    def on_save_ts():
        val = ts_var.get().strip()
        if not saved_user:
            messagebox.showerror("No user", "No saved user to attach timestamp to.", parent=dlg)
            return
        # basic validation
        if val:
            try:
                datetime.datetime.fromisoformat(val)
            except Exception:
                messagebox.showerror("Invalid", "Invalid ISO timestamp format.", parent=dlg)
                return
        try:
            store.set_os_credential_timestamp(saved_user, val if val else None)
            messagebox.showinfo("Saved", "Stored timestamp updated.", parent=dlg)
            refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=dlg)

    btn_frame = ttk.Frame(frm)
    btn_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
    ttk.Button(btn_frame, text="Refresh", command=refresh).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Remove OS saved login", command=on_remove).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Save stored timestamp", command=on_save_ts).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Close", command=lambda: dlg.destroy()).pack(side=tk.LEFT)

    refresh()
    dlg.wait_window()
    return None
