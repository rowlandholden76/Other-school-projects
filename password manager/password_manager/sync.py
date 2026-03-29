"""Synchronization helpers for reconciling per-entry vault and OS credentials.

This module contains testable functions implementing the "newest wins"
reconciliation between the JSON vault (PasswordStore) and the OS credential
store. It avoids GUI interactions and returns a summary of actions taken so
callers can present user-facing messages as needed.
"""
from typing import Any, Dict, List, Optional
import datetime
import logging

from .wincred import enumerate_entry_credentials, set_entry_credential, get_credential_with_time

logger = logging.getLogger(__name__)


def _parse_iso(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def reconcile_user_with_os(store: Any, owner: str, user_password: str) -> Dict[str, List[str]]:
    """Reconcile entries for `owner` between `store` and OS credentials.

    Returns a dict with keys `updated_vault` and `updated_os` listing entry
    names that were changed.
    """
    updated_vault: List[str] = []
    updated_os: List[str] = []

    # enumerate OS credentials produced by this app
    try:
        os_entries = enumerate_entry_credentials()
    except Exception:
        os_entries = []

    # Build map of OS entries for current user
    os_map: Dict[str, Dict[str, Any]] = {}
    for e in os_entries:
        if e.get("owner") != owner:
            continue
        name = e.get("entry_name")
        os_map[name] = e

    try:
        vault_names = store.list_entries(owner)
    except Exception:
        vault_names = []

    all_names = set(vault_names) | set(os_map.keys())

    for name in sorted(all_names):
        try:
            vault_entry = store.get_entry(owner, name, user_password)
        except Exception:
            vault_entry = None

        vault_ts_iso = store.get_entry_os_timestamp(owner, name) if vault_entry is not None else None
        vault_dt = _parse_iso(vault_ts_iso)

        os_e = os_map.get(name)
        os_dt = os_e.get("last_written") if os_e else None

        # normalize to seconds
        if os_dt is not None:
            try:
                os_dt = os_dt.replace(microsecond=0)
            except Exception:
                pass
        if vault_dt is not None:
            try:
                vault_dt = vault_dt.replace(microsecond=0)
            except Exception:
                pass

        # Decide winner
        if os_dt and (vault_dt is None or os_dt > vault_dt):
            # update vault from OS
            try:
                os_uname = os_e.get("username") if os_e else ""
                os_pwd = os_e.get("password") if os_e else ""
                store.add_entry(owner, name, os_uname or "", os_pwd or "", user_password, source={"type": "os", "name": "windows-credential-manager"})
                store.set_entry_os_timestamp(owner, name, os_dt.isoformat())
                updated_vault.append(name)
            except Exception:
                logger.exception("Failed to update vault from OS for %s/%s", owner, name)
        elif vault_dt and (os_dt is None or vault_dt > os_dt):
            # update OS from vault
            try:
                uname = vault_entry.get("username") if vault_entry else ""
                pwd = vault_entry.get("password") if vault_entry else ""
                set_entry_credential(owner, name, uname or "", pwd or "")
                # refresh timestamp from OS and store it
                try:
                    _, new_dt = get_credential_with_time(f"PasswordManager::{owner}::{name}", uname or "")
                    if new_dt is not None:
                        try:
                            new_dt_norm = new_dt.replace(microsecond=0)
                        except Exception:
                            new_dt_norm = new_dt
                        store.set_entry_os_timestamp(owner, name, new_dt_norm.isoformat())
                except Exception:
                    pass
                updated_os.append(name)
            except Exception:
                logger.exception("Failed to update OS from vault for %s/%s", owner, name)
        else:
            # timestamps equal or both missing — nothing to do
            pass

    return {"updated_vault": updated_vault, "updated_os": updated_os}
