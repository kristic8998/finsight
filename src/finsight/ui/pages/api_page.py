"""API Explorer page: compose a REST request, send it off-thread, inspect it."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...modules.api_explorer import (
    HTTP_METHODS,
    ApiExplorer,
    ApiRequest,
    ApiResponse,
    format_json,
    parse_headers,
    parse_params,
)
from ..widgets import ALERT, GOOD, WATCH, run_in_thread


class ApiPage(ctk.CTkFrame):
    def __init__(self, master: tk.Misc, app) -> None:  # noqa: ANN001
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.ctx = app.context
        self._api = ApiExplorer(max_history=self.ctx.config.api.max_history)

        ctk.CTkLabel(self, text="API Explorer", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="Test REST endpoints, payment/CRM backends, and JSON services — "
            "GET/POST, headers, body, and response-time tracking. Requests run off "
            "the UI thread.",
            font=ctk.CTkFont(size=12),
            text_color=("gray35", "gray65"),
        ).pack(anchor="w", pady=(0, 8))

        # ---- request line -----------------------------------------------------
        line = ctk.CTkFrame(self, fg_color="transparent")
        line.pack(fill="x")
        self._method = ctk.CTkOptionMenu(line, values=list(HTTP_METHODS), width=110)
        self._method.set("GET")
        self._method.pack(side="left", padx=(0, 6))
        self._url = ctk.CTkEntry(line, placeholder_text="https://api.example.com/v1/resource")
        self._url.pack(side="left", fill="x", expand=True, padx=6)
        self._send = ctk.CTkButton(line, text="Send", width=90, command=self._on_send)
        self._send.pack(side="left", padx=(6, 0))

        # ---- request editor ---------------------------------------------------
        req_tabs = ctk.CTkTabview(self, height=170)
        req_tabs.pack(fill="x", pady=(8, 0))
        for tab in ("Headers", "Params", "Body"):
            req_tabs.add(tab)
        self._headers = ctk.CTkTextbox(req_tabs.tab("Headers"))
        self._headers.pack(fill="both", expand=True)
        self._headers.insert("1.0", "# One per line, e.g.\nAccept: application/json\n")
        self._params = ctk.CTkTextbox(req_tabs.tab("Params"))
        self._params.pack(fill="both", expand=True)
        self._params.insert("1.0", "# key=value per line, e.g.\n# page=1\n")
        body_frame = req_tabs.tab("Body")
        body_bar = ctk.CTkFrame(body_frame, fg_color="transparent")
        body_bar.pack(fill="x")
        ctk.CTkLabel(body_bar, text="JSON / raw body (POST, PUT, PATCH)").pack(side="left")
        ctk.CTkButton(body_bar, text="Format JSON", width=110, command=self._format_body).pack(
            side="right"
        )
        self._body = ctk.CTkTextbox(body_frame)
        self._body.pack(fill="both", expand=True)

        # ---- response ---------------------------------------------------------
        self._status = ctk.CTkLabel(
            self, text="No request sent yet.", anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        )
        self._status.pack(fill="x", pady=(10, 2))
        resp_tabs = ctk.CTkTabview(self)
        resp_tabs.pack(fill="both", expand=True)
        for tab in ("Body", "Headers"):
            resp_tabs.add(tab)
        self._resp_body = ctk.CTkTextbox(resp_tabs.tab("Body"), wrap="none")
        self._resp_body.pack(fill="both", expand=True)
        self._resp_headers = ctk.CTkTextbox(resp_tabs.tab("Headers"), wrap="none")
        self._resp_headers.pack(fill="both", expand=True)
        self._resp_tabs = resp_tabs

    # ---- helpers --------------------------------------------------------------
    def _format_body(self) -> None:
        current = self._body.get("1.0", "end")
        self._body.delete("1.0", "end")
        self._body.insert("1.0", format_json(current))

    def _build_request(self) -> ApiRequest:
        return ApiRequest(
            method=self._method.get(),
            url=self._url.get(),
            headers=parse_headers(self._headers.get("1.0", "end")),
            params=parse_params(self._params.get("1.0", "end")),
            body=self._body.get("1.0", "end").strip(),
            timeout=self.ctx.config.api.timeout_seconds,
        )

    # ---- send -----------------------------------------------------------------
    def _on_send(self) -> None:
        try:
            request = self._build_request()
            request.validate()
        except ValueError as exc:
            self.app.toast.show(str(exc), "error")
            return
        self._send.configure(state="disabled", text="…")
        self._status.configure(text=f"{request.normalized_method()} {request.url} — sending…")
        run_in_thread(
            self,
            self.ctx.runner.submit,
            lambda: self._api.send(request),
            self._render,
            self._failed,
        )

    def _failed(self, exc: BaseException) -> None:
        self._send.configure(state="normal", text="Send")
        self.app.toast.show(f"Request failed: {exc}", "error")

    def _render(self, response: ApiResponse) -> None:
        self._send.configure(state="normal", text="Send")
        color = GOOD if response.ok else (WATCH if response.status_code else ALERT)
        self._status.configure(text=response.status_line(), text_color=color)

        self._resp_body.delete("1.0", "end")
        self._resp_body.insert("1.0", response.pretty_body() or "(empty body)")
        self._resp_headers.delete("1.0", "end")
        header_text = "\n".join(f"{k}: {v}" for k, v in response.headers.items())
        self._resp_headers.insert("1.0", header_text or "(no headers)")
        self._resp_tabs.set("Body")

        if response.error:
            self.app.toast.show("Request failed — see response", "error")
        else:
            self.app.toast.show(f"{response.status_code} in {response.elapsed_ms:.0f} ms", "ok")
