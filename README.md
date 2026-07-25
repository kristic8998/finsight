# FinSight 💠

**Enterprise lending analytics, automation & executive intelligence — one desktop app that replaces the pile of Excel sheets, SQL scripts, and manual MIS work inside an NBFC/FinTech lending team.**

Open it and everything already works: FinSight ships a realistic synthetic lending book (branches, officers, loans, EMI schedules with true delinquency behaviour), so the Executive dashboard, NLQ, analytics, and MIS generator are alive from the first minute. Connect Azure SQL / MS SQL Server when you're ready for production data.

![CI](https://github.com/kristic8998/finsight/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![UI](https://img.shields.io/badge/UI-CustomTkinter-2E7BE6)
![License](https://img.shields.io/badge/license-MIT-blue)

## What it does

| Module | One-click outcome |
|---|---|
| **Executive Command Center** | Business Health Score (0–100), 8 live KPI cards, branch ranking, DPD buckets, rule-based insights *with recommendations* |
| **Ask FinSight** | English question → SQL → table + chart + narrative. Offline, transparent, never guesses |
| **SQL Studio** | Query editor with highlighting, history, saved library, schema browser, Excel/CSV export, row-cap protection |
| **Excel Intelligence** | Merge, split, compare, profile, one-click clean (with audit trail), Excel ⇄ SQL |
| **Reconciliation Engine** | Ledger vs gateway/bank/settlement: auto-match, tolerance, duplicates, colour-coded difference workbook |
| **MIS Generator** | Daily/weekly/monthly packs: styled Excel workbook + board-ready HTML (print → PDF) |
| **AI Analytics** | 30-day collections forecast, anomaly detection, customer segmentation, loan risk scores — every result explains its method |
| **Automation Center** | Scheduled jobs (daily-at / every-N-min), folder watcher (statement lands → recon runs), full audited run log, email delivery |
| **MIS Studio** | The layman-friendly MIS engine: a zero-code **Visual Builder** (upload → pick Group by/Metric/Aggregate from your file's own headers → pivot + chart + formatted Excel), three **One-Click Lending Templates** (Daily Disbursement, Collection & DPD, Portfolio Health — CEO-ready workbooks from raw LMS exports), and a **Visual Auto-Reporter** that schedules any of them Daily/Weekly/Monthly like an alarm clock |
| **Data Quality Center** | One-click profiling for Excel/CSV/SQL — duplicates, missing values, IQR outliers, business-rule violations — a 0–100 quality score and an exportable exception workbook. Streams large CSVs in chunks |
| **API Explorer** | Test REST/JSON payment & CRM services (GET/POST/PUT/PATCH/DELETE): header & param editors, JSON pretty-print, response-time tracking — every call runs off the UI thread |
| **Plugins** | Drop a `.py` file into the plugins folder and it becomes a sidebar tool at next launch — no core edits. See [docs/PLUGINS.md](docs/PLUGINS.md) |
| **Productivity** | Notes, kanban task board, pinned favourites |
| **Platform** | Dark/light themes, **Ctrl+K command palette**, global search, keyboard shortcuts, auto-backup on exit, secure credential vault (Windows Credential Manager) |

## Install it (no Python required)

Most people want the packaged app, not the source. Grab it from the [Releases page](https://github.com/kristic8998/finsight/releases):

- **Installer** — `FinSight-Setup-1.5.0.exe`: run the wizard, get Start-menu shortcuts, per-user (no admin).
- **Portable** — `FinSight-1.5.0-portable.zip`: unzip anywhere and run `Start FinSight.bat`.

Both bundle their own Python, so the target PC needs nothing but Windows 10/11 64-bit. Full walkthrough — including building the exe, the Inno Setup installer, updating, and uninstalling — is in **[docs/INSTALL.md](docs/INSTALL.md)**.

## Quickstart from source (Windows, 5 minutes)

```bat
git clone https://github.com/kristic8998/finsight
cd finsight
scripts\install_windows.bat     :: creates .venv and installs everything
finsight --selftest             :: verifies all 20 subsystems on your machine
finsight                        :: launches the app
```

No configuration needed — the demo lending database is generated on first launch. Your data lives in `%LOCALAPPDATA%\FinSight` (settings, history, reports, automatic backups).

### Build the distributables

```bat
scripts\build_windows.bat        :: PyInstaller one-folder build -> dist\FinSight\
scripts\build_portable.bat       :: -> dist\FinSight-1.5.0-portable.zip
:: then compile installer\finsight.iss in Inno Setup -> FinSight-Setup-1.5.0.exe
```

### Connecting your real database (Azure SQL / MS SQL)

Settings → Database connections → fill server/database (+ username/password, or leave username blank for Windows auth) → Save → pick it as the **Active data source**. Passwords go to the Windows Credential Manager via `keyring` — never to disk in plain text. Requires `pip install pyodbc` and the [ODBC Driver 17+](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

> **Note:** the Executive/NLQ/Analytics modules read the canonical lending schema (`branches, officers, loans, payments, collection_targets` — see `docs/ARCHITECTURE.md`). Point them at your warehouse by creating views with those shapes; SQL Studio and Excel/Recon tools work against *any* schema as-is.

## Screenshots-in-words (first run)

Executive page: eight KPI cards over a 90-day collections chart, insight cards on the right ("PAR is 6.2% — run focused drives in Andheri, Salt Lake, Pune Camp"), full branch ranking below. Press **Ctrl+K**, type "recon", Enter — you're in the Reconciliation engine. Drop `sample_data/ledger_sample.xlsx` and `bank_sample.xlsx` in, click Reconcile: 2 mismatches, 1 missing, exportable colour-coded workbook.

## Design decisions (the honest table)

| Decision | Why |
|---|---|
| CustomTkinter desktop, no browser/Electron | Runs beautifully on a 16 GB integrated-graphics office laptop; zero server footprint; IT-friendly single venv |
| Bundled synthetic lending book | Beginner-friendly first run, deterministic tests, zero risk of shipping real customer data in a repo |
| Pattern-based NLQ, no cloud LLM | Lending data never leaves the laptop; answers are reproducible; unrecognised questions return suggestions instead of confident nonsense |
| Explainable models (linear trend, MAD z-scores, KMeans, logistic) | In finance you must defend every number to an auditor; each result ships its own explanation string |
| SQLite app-state + SQLAlchemy for MSSQL/Azure | Zero-config local persistence; production DBs via the same `ConnectionManager` |
| Row-capped query grid (50k default) | An accidental `SELECT *` on a big table must not kill the laptop; exports still use the full result |
| No PyAutoGUI screen automation | Brittle and risky on a corporate machine; the Automation Center does the same jobs through proper APIs |
| No OpenCV / Docker | No computer-vision problem here; a desktop app doesn't need a container. Scope discipline is a feature |

## Verify it yourself

```bat
finsight --selftest
```

runs the entire stack headless — demo data, KPIs, brief, NLQ, forecast, anomalies, segments, risk, recon, Excel tools, MIS pack, automation job, backup — and prints OK/FAIL per subsystem. The same suite runs in CI on Ubuntu **and Windows**, Python 3.10–3.12.

## Project structure

```
finsight/
├── src/finsight/
│   ├── core/        # config, logging, app-state DB, registry, tasks, backup, credentials, plugins
│   ├── data/        # connection manager, demo generator, LendingDataService (all KPI math)
│   ├── modules/     # executive, nlq, analytics, recon, excel_tools, mis, sql_studio, automation,
│   │                # productivity, data_quality, api_explorer — pure services, no UI imports
│   ├── ui/          # CustomTkinter shell, command palette, widgets, 12 pages
│   ├── plugins/     # drop-in sidebar extensions (example_toolkit.py) — see docs/PLUGINS.md
│   ├── app.py       # composition root + window shell (folds plugins into the sidebar)
│   └── selftest.py  # `finsight --selftest` end-to-end verification
├── tests/           # service tests + Data Quality, API Explorer & plugin-loader coverage
├── docs/            # install, user guide, troubleshooting, manual, architecture, dev guide
├── sample_data/     # recon + cleaning demo files
├── scripts/         # Windows install/run + PyInstaller & portable-zip build scripts
├── installer/       # Inno Setup script (finsight.iss) -> Setup.exe
└── .github/workflows/ci.yml
```

## Documentation

- **[Install Guide](docs/INSTALL.md)** — installer & portable, building from source, PyInstaller, Inno Setup installer, installing on a no-Python PC, updating, uninstalling
- **[User Guide](docs/USER_GUIDE.md)** — get productive fast; the areas, shortcuts, connecting your data
- **[Plugins](docs/PLUGINS.md)** — write a drop-in sidebar tool in one file (the plugin contract + a worked example)
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** — SmartScreen, antivirus, missing DLLs, build issues, logs
- **[User Manual](docs/USER_MANUAL.md)** — every module, step by step, written for a non-programmer
- **[Architecture](docs/ARCHITECTURE.md)** — layers, patterns (repository, service, DI), threading model, canonical schema
- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** — dev setup, adding a module, adding an automation job, building the .exe

## Roadmap (deliberately deferred, with reasons)

Power BI REST integration (needs Azure AD app registration in your tenant), SQL Server execution-plan viewer (SSMS does this better today), code-signing the installer/exe (needs a purchased certificate — until then SmartScreen shows a first-run prompt, see [TROUBLESHOOTING](docs/TROUBLESHOOTING.md)), configurable dashboard widget layout, and per-SKU schema mapping UI for non-canonical warehouses.

> **Packaging now ships:** the PyInstaller spec, portable-zip builder, and a full [Inno Setup installer](installer/finsight.iss) are in the repo. Because PyInstaller can't cross-compile, the actual `.exe`/`Setup.exe` must be built and smoke-tested on a Windows machine — see [docs/INSTALL.md](docs/INSTALL.md).

## License

MIT — see [LICENSE](LICENSE).
