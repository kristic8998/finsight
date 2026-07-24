# FinSight — User Guide

A practical, no-jargon guide to using FinSight day to day. If you haven't installed it yet, start with **[INSTALL.md](INSTALL.md)**. For an exhaustive screen-by-screen reference, see **[USER_MANUAL.md](USER_MANUAL.md)**; this guide gets you productive fast.

---

## What FinSight is

FinSight is a desktop suite for lending / NBFC / FinTech teams that puts an executive dashboard, plain-English data questions, analytics, reconciliation, Excel tooling, MIS report generation, a SQL studio, and light automation in one app. It runs fully offline on your laptop and ships with a **synthetic demo lending book**, so every screen has realistic data from the first launch — nothing you click can touch a real system until you connect one.

> **Data safety:** FinSight is built for synthetic or de-identified data. Do not load real customer PII/PHI into the demo environment. Connect a governed database when you're ready for real data, and keep credentials in the Windows Credential Manager (FinSight does this for you).

---

## First launch (3 minutes)

1. Start FinSight — **Start menu → FinSight**, the desktop icon, or `Start FinSight.bat` (portable). The first start creates your data folder at `%LOCALAPPDATA%\FinSight` and generates the demo book.
2. The **Executive** page opens first — the "CEO morning view."
3. Press **Ctrl+K** and type anything (`recon`, `theme`, `mis`) — the command palette jumps you there.
4. Press **Ctrl+D** to toggle dark/light.

If the dashboard renders with charts and numbers, your install is healthy.

---

## The nine areas

**Executive** — Business Health Score (0–100 with a grade), eight KPI cards, a 90-day collections chart, and colour-coded insight cards (green good / orange watch / red alert), each with a concrete recommendation. Click ↻ to recompute. Alert thresholds are yours to tune in Settings.

**Ask FinSight** — type plain-English questions like `top 5 branches by overdue` or `collections trend last 60 days`. You get a table, a chart, a one-line narrative, **and the SQL that produced it**. If it doesn't understand, it says so and shows examples — it never guesses with your numbers.

**Analytics** — collections forecasting, anomaly detection with plain-English explanations, customer segmentation, and per-loan risk scores. Runs on scikit-learn, tuned to be fast on a CPU-only laptop.

**Reconciliation** — match two data sources (e.g. a bank statement against your ledger) on a key + amount, and get matched / mismatched / missing breakdowns you can export.

**Excel Tools** — load a spreadsheet, standardise headers, trim text, drop blank/duplicate rows, and save a clean copy; push query results straight to `.xlsx`.

**MIS** — generate named business report packs (daily/portfolio/collections and more) as formatted Excel from a catalog of templates, with a record of recent reports.

**SQL Studio** — pick a connection, write SQL, **Ctrl+Enter** to run. Double-click a table to insert its name; save queries to the Library. On-screen results cap at 50,000 rows to protect your laptop; exports are complete.

**Automation / Productivity** — register and run small recurring jobs, and keep quick operational notes/tasks alongside your data work.

**Settings** — theme and branding, demo size, executive alert thresholds, and database connections (credentials go to the Windows Credential Manager, never plain text).

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| **Ctrl+K** | Command palette (jump to any page or action) |
| **Ctrl+D** | Toggle dark / light theme |
| **Ctrl+Enter** | Run the query (SQL Studio) |
| **↻ / F5** | Refresh the current page's data |

---

## Connecting your own data

1. **Settings → Connections → Add.**
2. Choose SQLite (point at a `.db` file) or SQL Server (host/database; requires the `mssql` extra if you built from source).
3. FinSight stores the credentials in the **Windows Credential Manager** and the connection details in its app database.
4. Switch the active connection from the selector at the top-right of data pages.

---

## Where your work is saved

Databases, backups, generated MIS packs, and logs live under `%LOCALAPPDATA%\FinSight` (or your `FINSIGHT_HOME` if you set one). This folder is independent of the app itself, so updating or reinstalling FinSight never loses your data. See [INSTALL.md → Where your data lives](INSTALL.md#where-your-data-lives).

---

## Getting help

- Something won't launch or a screen errors → **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.
- Deep reference for every control → **[USER_MANUAL.md](USER_MANUAL.md)**.
- Bugs / requests → [open an issue](https://github.com/kristic8998/finsight/issues).
