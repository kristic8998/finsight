# FinSight Developer Guide

## Dev setup

```bash
git clone https://github.com/kristic8998/finsight && cd finsight
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev]"        # add ,mssql for pyodbc
pytest                         # 62 tests, ~2 s
ruff check src tests && black --check src tests
finsight --selftest            # end-to-end, headless
finsight                       # launch the app
```

Linux/macOS note: install your OS's `python3-tk` package to run the GUI; tests and the
selftest are headless and run anywhere.

## Repo conventions

- `src/` layout, Python ≥ 3.10, `ruff` (E,F,W,I,UP,B,SIM @ 100 cols) + `black`.
- Services raise domain exceptions; UI translates them into toasts. No `print` outside CLI.
- Every service is constructed in `ui/context.py::build_context` — add new dependencies
  there and nowhere else.
- Tests isolate the filesystem via the `FINSIGHT_HOME` env var (see `tests/conftest.py`).

## Adding a module (page + service)

1. Write the service in `src/finsight/modules/yourthing.py` — pure Python, take dependencies
   through `__init__`, raise domain errors.
2. Add tests in `tests/` (the session fixtures give you a wired demo book).
3. Wire it in `ui/context.py` (`AppContext` field + `build_context`).
4. Create `ui/pages/yourthing_page.py` following any existing page: build widgets in
   `__init__`, refresh in `on_show()`, run work via `run_in_thread`.
5. Register in `ui/pages/__init__.py::PAGE_FACTORIES` and `app.py::_PAGES`. Sidebar,
   Ctrl+K palette, and search pick it up automatically.

## Adding an automation job

```python
def job_weekly_pack() -> str:
    output = context.mis.generate("weekly")
    return f"weekly MIS → {output.excel_path.name}"

context.automation.register_job("Generate weekly MIS", job_weekly_pack)
```

Registered jobs immediately support Run-now, daily/interval schedules, folder watches,
and audited logging.

## Building the Windows executable

On a Windows machine (PyInstaller cannot cross-compile):

```bat
scripts\build_windows.bat
```

produces `dist\FinSight\FinSight.exe` (one-folder build — starts faster and antivirus-friendlier
than one-file). Ship the whole `dist\FinSight` folder or zip it.

## Release checklist

1. `pytest` green, `ruff`/`black` clean, `finsight --selftest` all OK.
2. Bump version in `src/finsight/__init__.py` and `pyproject.toml`.
3. Update `CHANGELOG.md`.
4. Tag `vX.Y.Z`, create the GitHub release, attach the zipped Windows build if available.
