# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

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
