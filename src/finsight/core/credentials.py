"""Credential vault.

Secrets (database passwords, SMTP passwords) never touch YAML or the
app database. On Windows this uses the OS Credential Manager via
``keyring``; if keyring is unavailable the vault degrades to an
in-memory store for the session and says so loudly, rather than
silently writing plaintext to disk.
"""

from __future__ import annotations

import contextlib
import logging

logger = logging.getLogger(__name__)

_SERVICE = "FinSight"

try:  # pragma: no cover - environment dependent
    import keyring

    _KEYRING = True
except Exception:  # pragma: no cover
    keyring = None  # type: ignore[assignment]
    _KEYRING = False

_session_store: dict[str, str] = {}


def backend_name() -> str:
    """Human-readable description of where secrets are stored."""
    if _KEYRING:
        try:
            return f"OS keyring ({keyring.get_keyring().__class__.__name__})"
        except Exception:  # pragma: no cover
            return "OS keyring"
    return "session-only memory (install 'keyring' for persistent secure storage)"


def set_secret(name: str, value: str) -> None:
    if _KEYRING:
        try:
            keyring.set_password(_SERVICE, name, value)
            return
        except Exception as exc:  # pragma: no cover
            logger.warning("keyring unavailable (%s); using session store", exc)
    _session_store[name] = value


def get_secret(name: str) -> str | None:
    if _KEYRING:
        try:
            stored = keyring.get_password(_SERVICE, name)
            if stored is not None:
                return stored
        except Exception as exc:  # pragma: no cover
            logger.warning("keyring unavailable (%s); using session store", exc)
    return _session_store.get(name)


def delete_secret(name: str) -> None:
    if _KEYRING:
        with contextlib.suppress(Exception):  # not found / no backend
            keyring.delete_password(_SERVICE, name)
    _session_store.pop(name, None)
