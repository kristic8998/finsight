# FinSight Plugins

FinSight has a drop-in plugin system: a single `.py` file becomes a new
sidebar tool at the next launch, with **no changes to the core**. Use it
to add a team-specific utility without forking the app.

## Where plugins live

Two folders are scanned at startup:

| Folder | For |
|---|---|
| `src/finsight/plugins/` | plugins that ship *with* the app (built-ins) |
| `%LOCALAPPDATA%\FinSight\plugins\` | your own drop-ins — no reinstall, no rebuild |

Files whose names start with `_` are ignored. A plugin that fails to
import (missing dependency, syntax error, bad metadata) is **logged and
skipped** — one bad file never stops the app or the other plugins.

## The contract

Subclass `FinSightPlugin`, set four metadata attributes, and implement
`create_page`:

```python
import customtkinter as ctk
from finsight.core.plugins import FinSightPlugin


class WordCountPlugin(FinSightPlugin):
    id = "wordcount"          # unique, identifier-safe; also the sidebar route
    title = "Word Count"      # sidebar label
    icon = "¶"                # single glyph
    order = 500               # sort order (built-ins use 10–100; plugins default 500)

    def create_page(self, parent, app):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        box = ctk.CTkTextbox(frame)
        box.pack(fill="both", expand=True)
        out = ctk.CTkLabel(frame, text="0 words")
        out.pack(anchor="w")

        def count() -> None:
            out.configure(text=f"{len(box.get('1.0', 'end').split())} words")

        ctk.CTkButton(frame, text="Count", command=count).pack(anchor="w", pady=6)
        return frame
```

Drop that file in `%LOCALAPPDATA%\FinSight\plugins\`, restart FinSight,
and **Word Count** appears in the sidebar.

### What you get from `app`

`create_page(self, parent, app)` is called lazily the first time the user
opens your page. `parent` is the host frame; `app` is the running
window, so you can reach the whole application:

- `app.context` — every service (`app.context.data`, `.executive`, `.sql`, …)
- `app.context.runner` — the background thread pool; **run heavy work here**
- `app.toast` — status messages: `app.toast.show("Done", "ok")`
- `app.context.config` — typed configuration

Reuse the shared widgets in `finsight.ui.widgets` (`Section`, `KpiCard`,
`DataGrid`, `run_in_thread`) so your page matches the rest of the app.

## Keep the UI responsive

Anything slow — a query, a file read, an HTTP call — must run off the Tk
thread, exactly like the built-in pages:

```python
from finsight.ui.widgets import run_in_thread

def go() -> None:
    run_in_thread(
        frame,                        # any widget (for marshalling back to Tk)
        app.context.runner.submit,    # the thread pool
        lambda: do_expensive_work(),  # runs on a worker thread
        on_done,                      # called back on the Tk thread
        on_error,
    )
```

## Rules & gotchas

- **`id` must be unique and a valid Python identifier.** A plugin whose id
  collides with a built-in page (e.g. `sql`) is skipped — built-ins win.
- **Metadata is validated.** Empty `id`/`title` or a non-glyph `icon`
  makes the plugin skip with a logged reason.
- **Import cost is startup cost.** Keep module-level work light; do the
  heavy lifting inside `create_page` (and off-thread).
- **A worked example ships in the repo:** `src/finsight/plugins/example_toolkit.py`
  (hashing, base64, epoch↔date). Copy it as a starting point.

## How discovery works (under the hood)

`finsight.core.plugins.discover_plugins` scans both folders, imports each
file (built-ins by dotted name, user files straight from disk), finds
concrete `FinSightPlugin` subclasses, validates them, and returns a
`DiscoveryResult(plugins, errors)`. `Registry.load_plugins` then registers
each as a sidebar module, and the shell folds them into the navigation and
page router next to the built-in pages. All of this is covered by
`tests/test_plugins.py`.
