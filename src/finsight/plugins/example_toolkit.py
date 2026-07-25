"""Example plugin: a small developer/analyst toolkit.

Demonstrates the whole plugin contract in one file — metadata plus a
``create_page`` that builds a real CustomTkinter page using the app's
shared widgets. All operations are instant, pure-stdlib, and offline, so
no threading is needed. Copy this file as a starting point for your own
plugins; drop it in ``%LOCALAPPDATA%/FinSight/plugins/`` and restart.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import customtkinter as ctk

from ..core.plugins import FinSightPlugin


class ToolkitPlugin(FinSightPlugin):
    id = "toolkit"
    title = "Dev Toolkit"
    icon = "🛠"
    order = 500

    def create_page(self, parent: Any, app: Any) -> Any:
        return _ToolkitPage(parent, app)


class _ToolkitPage(ctk.CTkFrame):
    """Hashing, base64, and epoch↔date conversions for quick checks."""

    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Dev Toolkit", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Hashes, encodings, and timestamp conversions — a built-in plugin, "
            "loaded from finsight/plugins/example_toolkit.py.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 10))

        self._input = ctk.CTkTextbox(self, height=90)
        self._input.pack(fill="x")
        self._input.insert("1.0", "hello finsight")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", pady=8)
        for label, handler in (
            ("MD5", self._md5),
            ("SHA-256", self._sha256),
            ("Base64 encode", self._b64_encode),
            ("Base64 decode", self._b64_decode),
            ("Now → epoch", self._now_epoch),
            ("Epoch → UTC", self._epoch_to_utc),
            ("Pretty JSON", self._pretty_json),
        ):
            ctk.CTkButton(buttons, text=label, width=120, command=handler).pack(
                side="left", padx=3, pady=2
            )

        self._output = ctk.CTkTextbox(self, height=160)
        self._output.pack(fill="both", expand=True)

    # ---- helpers ----------------------------------------------------------
    def _text(self) -> str:
        return self._input.get("1.0", "end").strip()

    def _set(self, value: str) -> None:
        self._output.delete("1.0", "end")
        self._output.insert("1.0", value)

    def _fail(self, message: str) -> None:
        self._set(f"⚠ {message}")
        if hasattr(self.app, "toast"):
            self.app.toast.show(message, "error")

    # ---- operations -------------------------------------------------------
    def _md5(self) -> None:
        self._set(hashlib.md5(self._text().encode("utf-8")).hexdigest())

    def _sha256(self) -> None:
        self._set(hashlib.sha256(self._text().encode("utf-8")).hexdigest())

    def _b64_encode(self) -> None:
        self._set(base64.b64encode(self._text().encode("utf-8")).decode("ascii"))

    def _b64_decode(self) -> None:
        try:
            self._set(base64.b64decode(self._text().encode("ascii")).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface any decode error to the user
            self._fail(f"not valid base64: {exc}")

    def _now_epoch(self) -> None:
        now = datetime.now(tz=timezone.utc)
        self._set(f"{int(now.timestamp())}   ({now.isoformat(timespec='seconds')})")

    def _epoch_to_utc(self) -> None:
        raw = self._text()
        try:
            moment = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            self._fail(f"not a valid epoch: {exc}")
            return
        self._set(moment.isoformat(timespec="seconds"))

    def _pretty_json(self) -> None:
        try:
            parsed = json.loads(self._text())
        except json.JSONDecodeError as exc:
            self._fail(f"not valid JSON: {exc}")
            return
        self._set(json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True))
