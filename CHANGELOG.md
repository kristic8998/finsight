# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [1.5.1] — 2026-07-26

Packaging fix: the v1.5.0 tag was cut while the five new MIS Studio engine files were missing from the repository (a failed web upload), so its source snapshot could not import `finsight.modules.mis_builder` and friends. No code changes beyond re-adding those files, pinning ruff's `known-first-party` for CI/local parity, and this version bump. Use this tag instead of v1.5.0.

## [1.5.0] — 2026-07-25

The "Layman-Friendly MIS Engine" — a new **MIS Studio** page (sidebar, between MIS Reports and Analytics) with three tabs, each carrying a permanent How-to-Use card, friendly error popups instead of crashes, and background-threaded pandas throughout.

### Added
- **Visual MIS Builder** (`modules/mis_builder.py`, Builder tab): zero-code pivot wizard — upload any CSV/Excel, dropdowns fill with the file's own headers, pick Group by / Metric / Aggregate (Sum, Average, Count, Min, Max) plus an optional Split-by second dimension → instant pivot with a TOTAL row, an embedded matplotlib chart, formatted Excel export, and named "recipes" saved for the Auto-Reporter.
- **One-Click Lending Templates** (`modules/mis_templates.py`, Templates tab): three giant buttons — *Daily Disbursement MIS*, *Collection & DPD MIS* (DPD buckets, PAR 30/90, collection efficiency), *Portfolio Health Report* (book size, concentration with share %, top 20 exposures). Columns detected by name from raw LMS exports; wrong files raise a plain-English `TemplateError` shown as a friendly popup; exports are CEO-ready multi-sheet workbooks via a shared house style (`modules/excel_style.py`).
- **Visual Auto-Reporter** (`modules/auto_reporter.py`, Auto-Reporter tab): alarm-clock scheduling — pick a template or saved recipe, a source file, Daily/Weekly/Monthly + time, click *Activate Automation*. Jobs persist to JSON, fire from a daemon loop (stdlib threading, no new dependency), reschedule after success *and* failure, and log to an in-app activity feed. Honest scope stated in the UI: runs while FinSight is open.
- Shared UX widgets: `HelperCard` (the mandatory 1-2-3 guide) and `FriendlyDialog`/`show_friendly_error`; `DataGrid` gained row selection (used by the jobs list). Deterministic `modules/mis_samples.py` powers every "Try with sample data" button.

### Changed
- Self-test now covers 20 subsystems (+ mis builder, mis templates, auto reporter). Test suite grows to 155 (+33 for the new engines, including monthly-clamp and failure-reschedule scheduler cases). No new runtime dependencies.

## [1.4.0] — 2026-07-25

Phase 2 expansion — three new architectural components, all non-blocking and lightweight for a 16 GB integrated-graphics laptop.

### Added
- **Data Quality Center** (`modules/data_quality.py`, `ui/pages/dq_page.py`): one-click profiling for Excel, CSV, and SQL — per-column stats, duplicate rows, duplicate keys, missing/empty/constant columns, negative amounts, IQR outliers, and whitespace issues, rolled into a 0–100 quality score with grade and an exportable three-sheet exception workbook. Large CSVs stream through a chunked accumulator so the same report is produced whether a file is profiled whole or in chunks (asserted by tests).
- **API Explorer** (`modules/api_explorer.py`, `ui/pages/api_page.py`): a lightweight REST client for testing payment/CRM/JSON services — GET/POST/PUT/PATCH/DELETE, header & param editors, JSON pretty-printing, and response-time tracking. Transport errors become inspectable responses rather than crashes; a capped in-session history is kept. Every call runs on the `TaskRunner`, never on the Tk thread.
- **Plugin architecture** (`core/plugins.py`, enhanced `core/registry.py`, new `plugins/` package): drop a `.py` file defining a `FinSightPlugin` subclass into `finsight/plugins/` or `%LOCALAPPDATA%/FinSight/plugins/` and it is discovered at startup and mounted in the sidebar — no core edits. Discovery is defensive (a broken plugin is logged and skipped) and the shell folds plugins into the navigation and page router alongside built-in pages. Ships a worked example, `plugins/example_toolkit.py`, and an authoring guide, `docs/PLUGINS.md`.

### Changed
- `requests>=2.31` added as a runtime dependency (API Explorer).
- New optional config sections `data_quality` (chunk size, missing-alert threshold) and `api` (timeout, history size); existing `config.yaml` files remain valid.
- Self-test now covers 17 subsystems (adds data quality, API explorer, plugin discovery). Test suite gains 33 tests across the three new components (`test_data_quality.py`, `test_api_explorer.py`, `test_plugins.py`), all green under ruff + black on Windows and Ubuntu.

## [1.3.0] — 2026-07-24

Windows distribution & documentation release — nothing changes in the app's behaviour; everything changes in how you install and hand it off.

### Added
- **Inno Setup installer** (`installer/finsight.iss`): per-user install (no admin), Start-menu + optional desktop shortcuts, in-place upgrades via a fixed `AppId`, and an auto-generated uninstaller registered in *Apps & features*
- **Portable build** (`scripts/build_portable.bat`): produces a self-contained `FinSight-1.3.0-portable.zip` with a `Start FinSight.bat` launcher and a plain-language read-me — no install, no admin, no Python on the target PC
- **Hardened build script** (`scripts/build_windows.bat`): auto-creates the venv, installs dev extras, runs the self-test as a pre-flight, then freezes a clean one-folder PyInstaller build
- **[docs/INSTALL.md](docs/INSTALL.md)**: end-to-end Windows guide — Python version, venv, dependencies, configuration, PyInstaller build, portable + installer packaging, installing on a **no-Python** machine, updating after future releases, and uninstalling (with data-removal notes)
- **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**: fast, task-oriented guide to the nine areas, shortcuts, and connecting your own data
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**: SmartScreen, antivirus false positives, missing VC++ runtime, hidden-import build errors, high-DPI issues, and log collection

### Notes
- The installer/exe are not code-signed, so Windows SmartScreen shows a first-run prompt (documented). Code-signing needs a purchased certificate and is on the roadmap.
- Because PyInstaller cannot cross-compile, the `.exe`/`Setup.exe` artifacts must be built and smoke-tested on a Windows machine; the scripts and installer script are validated in the repo, and CI continues to verify the code on Windows + Ubuntu across Python 3.10–3.12.

## [1.2.0] — 2026-07-24

### Added
- **Root Cause Analyzer**: every reconciliation now explains its difference — decomposition into missing/duplicates/amount-mismatch causes with amount impact, share %, and recommended fixes; narrative shown on the Recon page and an Investigation sheet added to the difference workbook
- **Typo-pair detection**: unmatched keys on both sides are fuzzy-compared (stdlib difflib) to surface likely key-format issues ("UTR-9001" ≈ "UTR9001") with a Possible Typos sheet
- **Data Quality Score**: Excel profiler now reports a composite 0–100 score (completeness / uniqueness / consistency) with grade and notes

## [1.1.0] — 2026-07-24

### Added
- **Business MIS catalog**: six named one-click reports — Collections MIS, Disbursement MIS, Recovery & Overdue MIS, Branch MIS, Employee MIS, Product MIS — each a styled multi-sheet workbook (or per-section CSV) built from the same read-model as the dashboard
- **Custom report templates**: compose your own MIS from 13 named sections, save it, regenerate daily; templates persist in the app database
- **CSV export format** for catalog reports
- **Company branding**: Settings → Branding stamps your company name on every report pack
- **Recent reports** list on the MIS page (double-click to open) and configurable report window (days)

## [1.0.0] — 2026-07-24

### Added
- Executive Command Center: Business Health Score, 8 KPI cards, branch ranking, DPD buckets, product mix, rule-based insights with recommendations
- Ask FinSight: offline pattern-based natural-language querying with transparent SQL, charts, and narratives
- SQL Studio: highlighted editor, background execution with timer, history, saved library with starter queries, schema browser, Excel/CSV export, row-cap protection
- Excel Intelligence: merge, split, compare, profile, one-click clean with audit trail, Excel ⇄ SQL
- Reconciliation Engine: keyed matching with amount tolerance, duplicate detection, colour-coded multi-sheet difference workbook
- MIS Generator: daily/weekly/monthly packs (styled Excel with embedded trend chart + board-ready HTML)
- AI Analytics: collections forecast (trend + weekday seasonality), MAD-based anomaly detection, KMeans customer segments with business labels, logistic loan risk scores — all with plain-English method explanations
- Automation Center: named jobs, daily-at/interval scheduler, folder watcher, audited run log, SMTP report delivery with retry
- Productivity: notes, kanban task board, favorites
- Platform: dark/light themes, Ctrl+K command palette, global search registry, keyboard shortcuts, auto-backup with rotation, secure credential vault (Windows Credential Manager), synthetic demo lending book, `finsight --selftest`
- 62-test suite, ruff+black clean, CI on Ubuntu & Windows across Python 3.10–3.12, Windows install/run/build scripts, PyInstaller spec
