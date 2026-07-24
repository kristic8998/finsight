# FinSight User Manual

Written for the daily operator — no programming knowledge assumed.

## 1. First launch

Run `finsight` (or double-click `scripts\run_finsight.bat`). The first start creates your
personal data folder at `%LOCALAPPDATA%\FinSight` and a **demo lending book** so every screen
has live data. Nothing you do in the demo can touch real systems.

**Get comfortable in 3 minutes:**
1. The **Executive** page opens first — that's the CEO morning view.
2. Press **Ctrl+K** and type anything ("recon", "theme", "mis") — Enter jumps there.
3. Press **Ctrl+D** to switch dark/light.

## 2. Executive Command Center

Click ↻ Refresh to recompute. You get: the Business Health Score (0–100 with grade), eight
KPI cards, a 90-day collections chart, insight cards (colour = severity: green good, orange
watch, red alert — each with a concrete recommendation), and the full branch ranking.
Thresholds that trigger alerts are yours to tune in **Settings → Executive alert thresholds**.

## 3. Ask FinSight (plain-English questions)

Type questions like:
- `top 5 branches by overdue`
- `collections trend last 60 days`
- `overdue loans in Andheri`
- `collection efficiency by branch`
- `business summary`

You always see: the answer table, a chart, a one-line narrative, and the SQL that produced it.
If FinSight doesn't understand, it says so and shows examples — it never guesses with your
numbers.

## 4. SQL Studio

Pick a connection (top-right), type SQL, **Ctrl+Enter** to run. Double-click a table on the
left to insert its name; the **Library** tab holds starter queries plus anything you save.
Results are capped at 50,000 rows on screen to protect your laptop — exports contain
everything. **Export…** writes Excel or CSV.

## 5. Excel Intelligence

Six buttons, each fully guided by file pickers:
**Merge** stacks same-layout files (adds a `source_file` column) · **Split** breaks one file
into one file per value of a column · **One-click clean** trims spaces, fixes headers, drops
duplicates/empty rows, detects date columns — and lists every action it took · **Profile**
shows missing %, uniques, and types per column · **Compare** diffs two files on a key ·
**Excel → SQL** loads a spreadsheet into a database table.

## 6. Reconciliation

1. Pick the two files (ledger vs statement — any two spreadsheets/CSVs).
2. FinSight guesses the key (UTR/ref/ID) and amount columns — adjust if needed.
3. Set a tolerance (e.g. `1` = differences up to ₹1 count as matched).
4. **Reconcile** → tabs for Mismatches, Only-Left, Only-Right, Matched, Duplicates.
5. **Export difference report** → a colour-coded multi-sheet workbook for the auditors.

Sample files to practice with are in `sample_data/`.

## 7. MIS Reports

Choose daily / weekly / monthly → **Generate**. You get an Excel pack (Summary with embedded
trend chart, Branches, DPD, Product Mix, Insights, Trend Data) and an HTML report — open it
and print → *Save as PDF* for the board copy. Files land in
`%LOCALAPPDATA%\FinSight\reports`; the page has an *Open reports folder* button.

## 8. Analytics

Four buttons: **Forecast** (next 30 days of collections, trend + weekday pattern),
**Anomalies** (days that don't fit history), **Segments** (customers grouped into named
behaviour tiers), **Risk scores** (0–100 stress score per active loan). Every result shows
the method in plain English. On demo data these teach; on your book they inform — retrain
mentally before trusting.

## 9. Automation

- **Run now**: pick a job, click run — result and status land in the log below.
- **Schedule**: job + "daily at 07:30" (or every N minutes) → add → switch **Scheduler
  running** on.
- **Watch a folder**: when a matching file (e.g. `*.xlsx`) appears, the chosen job fires.
  Classic setup: watch your downloads folder for bank statements, auto-generate the MIS.
- Every run is recorded — job, status, detail, time. Automation you can audit.

## 10. Productivity, Settings & data safety

Notes and a To-do/Doing/Done board live under **Productivity** (Ctrl+S saves the open note).
**Settings** holds themes, start page, alert thresholds, database connections, and email
(SMTP) for report delivery — passwords are stored in the **Windows Credential Manager**,
never in files. FinSight backs itself up automatically every time you close it (last 10
archives kept in `%LOCALAPPDATA%\FinSight\backups`); Settings → *Back up now* any time.

## 11. If something goes wrong

Run `finsight --selftest` from a terminal — it tests all 14 subsystems and prints exactly
which one failed. Logs live in `%LOCALAPPDATA%\FinSight\logs\finsight.log`.
