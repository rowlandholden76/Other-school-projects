"""OS credential helpers.

This module provides small wrappers around the `keyring` library and the
Windows Credential API. It focuses on robust logging and clearer error
reporting so callers (the GUI) can decide how to proceed when OS credential
operations fail.

Public helpers:
- `set_credential(service, username, password)` — set an OS credential (may raise `CredentialError`).
- `get_credential(service, username)` — return stored password or `None`.
- `delete_credential(service, username)` — remove credential (no-op if missing).
- `get_credential_with_time(service, username)` — return `(password|None, datetime|None)`.
"""
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CredentialError(Exception):
    """Raised when an OS credential operation fails irrecoverably."""


try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover - environment may not have keyring
    keyring = None


def set_credential(service: str, username: str, password: str) -> None:
    """Store a credential via `keyring`.

    Raises `CredentialError` when the operation cannot be performed (e.g.
    when `keyring` is not available or the backend raises an error).
    """
    if keyring is None:
        logger.error("keyring not available; cannot set credential for %s/%s", service, username)
        raise CredentialError("keyring library is required for credential manager integration")
    try:
        keyring.set_password(service, username, password)
        logger.debug("OS credential set for %s/%s", service, username)
    except Exception as exc:
        logger.exception("Failed to set OS credential for %s/%s: %s", service, username, exc)
        raise CredentialError("Failed to set OS credential") from exc


def get_credential(service: str, username: str) -> Optional[str]:
    """Return the stored password for `service`/`username` or `None`.

    This function never raises if `keyring` operations fail; instead it logs
    the problem and returns `None` so callers can fall back to alternative
    flows.
    """
    if keyring is None:
        logger.debug("keyring not available; get_credential(%s, %s) -> None", service, username)
        return None
    try:
        pwd = keyring.get_password(service, username)
        logger.debug("keyring.get_password returned %s for %s/%s", "<hidden>" if pwd else None, service, username)
        return pwd
    except Exception as exc:
        logger.exception("keyring.get_password failed for %s/%s: %s", service, username, exc)
        return None


def delete_credential(service: str, username: str) -> None:
    """Delete an OS credential. Failures are logged but treated as non-fatal."""
    if keyring is None:
        logger.debug("keyring not available; delete_credential(%s, %s) skipped", service, username)
        return
    try:
        keyring.delete_password(service, username)
        logger.debug("OS credential deleted for %s/%s", service, username)
    except Exception as exc:
        logger.exception("Failed to delete OS credential for %s/%s (may not exist): %s", service, username, exc)
        # ignore to keep behavior simple for callers
        return


# Advanced Windows-only helper to read credential and its LastWritten timestamp.
# Returns (password or None, datetime or None).
def get_credential_with_time(service: str, username: str) -> Tuple[Optional[str], Optional["datetime.datetime"]]:
    pwd = None
    # Try keyring first (cross-platform)
    if keyring is not None:
        try:
            pwd = keyring.get_password(service, username)
            logger.debug("keyring.get_password succeeded for %s/%s", service, username)
        except Exception as exc:
            logger.exception("keyring.get_password failed for %s/%s: %s", service, username, exc)
            pwd = None

    # On Windows, try to read LastWritten via Win32 API. Failures here are
    # non-fatal — we return (pwd, None) if the timestamp can't be determined.
    try:
        import ctypes
        import ctypes.wintypes
        import datetime

        CRED_TYPE_GENERIC = 1
        adv = ctypes.windll.advapi32
        CredReadW = adv.CredReadW
        CredFree = adv.CredFree
        CredReadW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        CredReadW.restype = ctypes.wintypes.BOOL
        CredFree.argtypes = [ctypes.c_void_p]

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.wintypes.DWORD), ("dwHighDateTime", ctypes.wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.wintypes.DWORD),
                ("Type", ctypes.wintypes.DWORD),
                ("TargetName", ctypes.wintypes.LPWSTR),
                ("Comment", ctypes.wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", ctypes.wintypes.DWORD),
                ("CredentialBlob", ctypes.c_void_p),
                ("Persist", ctypes.wintypes.DWORD),
                ("AttributeCount", ctypes.wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.wintypes.LPWSTR),
                ("UserName", ctypes.wintypes.LPWSTR),
            ]

        p = ctypes.c_void_p()
        ok = CredReadW(service, CRED_TYPE_GENERIC, 0, ctypes.byref(p))
        if not ok:
            logger.debug("CredReadW returned false for %s/%s", service, username)
            return pwd, None
        try:
            cred = ctypes.cast(p, ctypes.POINTER(CREDENTIAL)).contents
            ft = (cred.LastWritten.dwHighDateTime << 32) | cred.LastWritten.dwLowDateTime
            if ft == 0:
                logger.debug("Credential LastWritten FILETIME is zero for %s/%s", service, username)
                return pwd, None
            unix_ts = (ft - 116444736000000000) / 10_000_000
            dt = datetime.datetime.fromtimestamp(unix_ts)
            logger.debug("Win32 LastWritten for %s/%s = %s", service, username, dt.isoformat())
            return pwd, dt
        finally:
            try:
                CredFree(p)
            except Exception as exc:
                logger.exception("CredFree failed for %s/%s: %s", service, username, exc)
    except Exception as exc:
        logger.exception("Failed reading Win32 credential for %s/%s: %s", service, username, exc)
        return pwd, None


def _format_entry_target(owner: str, entry_name: str) -> str:
    return f"PasswordManager::{owner}::{entry_name}"


def set_entry_credential(owner: str, entry_name: str, entry_username: str, entry_password: str) -> None:
    """Store a per-entry credential using a deterministic target name.

    Raises `CredentialError` if the backend doesn't support storing.
    """
    target = _format_entry_target(owner, entry_name)
    set_credential(target, entry_username, entry_password)


def enumerate_entry_credentials(prefix: str = "PasswordManager::") -> list:
    """Enumerate OS credentials matching the given prefix (Windows only).

    Returns a list of dicts with keys: owner, entry_name, username, password, last_written (datetime|None).
    On non-Windows platforms or when enumeration fails, returns an empty list.
    """
    results = []
    try:
        import ctypes
        import ctypes.wintypes
        import datetime

        adv = ctypes.windll.advapi32
        CredEnumerateW = adv.CredEnumerateW
        CredFree = adv.CredFree
        CredEnumerateW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p)]
        CredEnumerateW.restype = ctypes.wintypes.BOOL
        CredFree.argtypes = [ctypes.c_void_p]

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.wintypes.DWORD), ("dwHighDateTime", ctypes.wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.wintypes.DWORD),
                ("Type", ctypes.wintypes.DWORD),
                ("TargetName", ctypes.wintypes.LPWSTR),
                ("Comment", ctypes.wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", ctypes.wintypes.DWORD),
                ("CredentialBlob", ctypes.c_void_p),
                ("Persist", ctypes.wintypes.DWORD),
                ("AttributeCount", ctypes.wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.wintypes.LPWSTR),
                ("UserName", ctypes.wintypes.LPWSTR),
            ]

        count = ctypes.wintypes.DWORD()
        pcreds = ctypes.c_void_p()
        filter_str = prefix + "*"
        ok = CredEnumerateW(filter_str, 0, ctypes.byref(count), ctypes.byref(pcreds))
        if not ok or count.value == 0:
            return results

        array_type = ctypes.c_void_p * count.value
        creds_array = ctypes.cast(pcreds, ctypes.POINTER(array_type)).contents
        for i in range(count.value):
            cred_ptr = creds_array[i]
            cred = ctypes.cast(cred_ptr, ctypes.POINTER(CREDENTIAL)).contents
            target = cred.TargetName
            uname = cred.UserName
            ft = (cred.LastWritten.dwHighDateTime << 32) | cred.LastWritten.dwLowDateTime
            last_written = None
            if ft != 0:
                unix_ts = (ft - 116444736000000000) / 10_000_000
                last_written = datetime.datetime.fromtimestamp(unix_ts)

            # parse target into owner and entry_name
            try:
                _, owner, entry_name = target.split("::", 2)
            except Exception:
                # unexpected target format; skip
                continue

            # attempt to retrieve password via keyring if available
            pwd = None
            if keyring is not None:
                try:
                    pwd = keyring.get_password(target, uname)
                except Exception:
                    pwd = None

            results.append({"owner": owner, "entry_name": entry_name, "username": uname, "password": pwd, "last_written": last_written})
        try:
            CredFree(pcreds)
        except Exception:
            logger.exception("CredFree failed during enumerate")
        return results
    except Exception:
        logger.exception("Credential enumeration not available on this platform or failed")
        return results
