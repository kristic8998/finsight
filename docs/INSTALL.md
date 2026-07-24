# FinSight — Windows Installation & Packaging Guide

This guide covers three audiences:

- **End users** who just want to run FinSight on Windows → [Option A: Installer](#option-a-installer-easiest) or [Option B: Portable](#option-b-portable-zip-no-install).
- **Anyone installing on a PC with no Python** → both A and B work; [see this note](#installing-on-a-pc-with-no-python).
- **Developers/packagers** who build the distributables → [Building from source](#building-from-source-for-developers) onward.

FinSight is a Windows desktop application (CustomTkinter). It targets **Windows 10/11, 64-bit, 16 GB RAM, Intel integrated graphics — no GPU required.**

---

## Quick decision: which install do I want?

| You want to… | Use | Needs Python? | Needs admin? |
|---|---|---|---|
| Click through a normal Setup wizard, get Start-menu shortcuts | **Installer** (`FinSight-Setup-1.3.0.exe`) | No | No (per-user) |
| Run from a USB stick / no install at all | **Portable** (`FinSight-1.3.0-portable.zip`) | No | No |
| Develop, modify, or build the app | **From source** (`pip install -e .`) | Yes, 3.10+ | No |

Both packaged options bundle their own Python — **the target PC does not need Python installed.**

---

## Option A: Installer (easiest)

1. Download **`FinSight-Setup-1.3.0.exe`** from the [Releases page](https://github.com/kristic8998/finsight/releases).
2. Double-click it. If Windows SmartScreen shows *"Windows protected your PC"*, click **More info → Run anyway** (this appears because the installer isn't code-signed; it is expected).
3. Follow the wizard. Default install location is `%LOCALAPPDATA%\Programs\FinSight` — **no administrator rights required**.
4. Optionally tick **Create a desktop shortcut**.
5. Finish, and launch from the **Start menu → FinSight** (or the desktop icon).

To remove it later, see [Uninstalling](#uninstalling).

---

## Option B: Portable (zip, no install)

1. Download **`FinSight-1.3.0-portable.zip`** from the [Releases page](https://github.com/kristic8998/finsight/releases).
2. Right-click the zip → **Extract All…** → choose any folder (Desktop, Documents, a USB drive — all fine).
3. Open the extracted folder and double-click **`Start FinSight.bat`** (or `FinSight\FinSight.exe`).
4. Same SmartScreen note as above: **More info → Run anyway** the first time.

Nothing is written to Program Files or the registry. To "uninstall," just delete the folder (your data under `%LOCALAPPDATA%\FinSight` is separate — see [Where your data lives](#where-your-data-lives)).

---

## Installing on a PC with no Python

**This is the normal case for the installer and the portable zip, and it just works.** PyInstaller bundles a complete Python runtime and every dependency *inside* the distributable. The target machine needs **only Windows 10/11 64-bit** — no Python, no `pip`, no internet connection.

- **Installer:** copy `FinSight-Setup-1.3.0.exe` to the other PC (USB or network share), run it, done.
- **Portable:** copy `FinSight-1.3.0-portable.zip`, unzip, run `Start FinSight.bat`, done.

You only need Python if you intend to **build** FinSight from source (next sections).

---

## Verifying an install worked

After installing on any machine, confirm the full stack is healthy:

- **Fastest:** launch FinSight; if the dashboard renders with demo data, you're good.
- **Thorough (from source only):** run the built-in self-test, which exercises every subsystem in ~30 seconds:

  ```bat
  finsight --selftest
  ```

  Every line should read `OK`, ending with `ALL CHECKS PASSED`. This is the same check the CI runs on every commit and the build script runs before freezing the exe.

---

# Building from source (for developers)

You only need this section if you want to modify FinSight or produce the packaged builds yourself.

## 1. Required Python version

**Python 3.10, 3.11, or 3.12 (64-bit).** 3.12 is recommended. Download from [python.org](https://www.python.org/downloads/windows/) and, on the first installer screen, **tick "Add python.exe to PATH."**

Verify in a new terminal:

```bat
python --version
```

## 2. Get the code

```bat
git clone https://github.com/kristic8998/finsight.git
cd finsight
```

(Or download the source zip from the Releases page and extract it.)

## 3. Create a virtual environment

A virtual environment keeps FinSight's dependencies isolated from other Python projects.

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

Your prompt now starts with `(.venv)`. Run everything below inside it. To leave later, type `deactivate`.

## 4. Install dependencies

FinSight's runtime dependencies (declared in `pyproject.toml`) are: `customtkinter`, `numpy`, `pandas`, `scikit-learn`, `matplotlib`, `SQLAlchemy`, `pydantic`, `PyYAML`, `openpyxl`, `keyring`.

Install the app (this pulls all of them automatically):

```bat
python -m pip install --upgrade pip
pip install -e .
```

For building the executable and running the tests, install the dev extras instead (adds `pyinstaller`, `pytest`, `black`, `ruff`):

```bat
pip install -e ".[dev]"
```

Optional: SQL Server connectivity adds `pyodbc` via `pip install -e ".[mssql]"`.

## 5. Configure the application

FinSight runs with sensible defaults and **needs no configuration to start** — on first launch it generates a synthetic demo database so you can explore immediately. Configuration is optional:

- **Data location:** by default everything lives in `%LOCALAPPDATA%\FinSight`. Override it by setting an environment variable before launching (useful for testing or a portable data folder):

  ```bat
  set FINSIGHT_HOME=D:\FinSightData
  finsight
  ```

- **Database connections:** add your own SQLite/SQL Server connections in-app via **Settings → Connections**. Credentials are stored in the **Windows Credential Manager** (via `keyring`), never in plain text.
- **In-app preferences:** theme, branding, and demo size are set under **Settings** and persisted in the app database.

## 6. Run from source

```bat
finsight            REM launches the desktop GUI
finsight --selftest REM runs the headless self-test
```

## 7. Build the executable (PyInstaller)

The repo ships a tested spec, `FinSight.spec` (a **one-folder** build — faster startup and friendlier with antivirus than one-file). The easiest path is the wrapper script:

```bat
scripts\build_windows.bat
```

It creates the venv if needed, installs dev extras, runs the self-test, then freezes the app. Result:

```
dist\FinSight\FinSight.exe   (plus a _internal\ support folder)
```

To run PyInstaller manually instead:

```bat
.venv\Scripts\activate.bat
pyinstaller FinSight.spec --noconfirm --clean
```

> **Why the build must run on Windows:** PyInstaller does **not** cross-compile. A Windows `.exe` can only be produced on Windows. Building on macOS/Linux yields a macOS/Linux binary, not a `.exe`.

## 8. Produce the two distributables

### Portable version

After the build above:

```bat
scripts\build_portable.bat
```

→ `dist\FinSight-1.3.0-portable.zip` — a self-contained folder with `FinSight.exe`, a `Start FinSight.bat` launcher, and a short read-me. Share that one zip; the recipient unzips and runs it.

### Installer version (Inno Setup)

1. Install **[Inno Setup 6+](https://jrsoftware.org/isdl.php)** (free).
2. Make sure `dist\FinSight\` exists (step 7).
3. Compile the bundled script `installer\finsight.iss`, either by opening it in the Inno Setup Compiler and pressing **Build (F9)**, or from a terminal:

   ```bat
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\finsight.iss
   ```

→ `installer\Output\FinSight-Setup-1.3.0.exe` — a standard wizard installer that creates shortcuts and a registered uninstaller. The full annotated script is in [`installer/finsight.iss`](../installer/finsight.iss).

---

## Updating the application after a future release

**Installer users:** download the newer `FinSight-Setup-x.y.z.exe` and run it. Inno Setup detects the existing install (same `AppId`) and upgrades in place — no need to uninstall first. Your data under `%LOCALAPPDATA%\FinSight` is untouched.

**Portable users:** download the new `FinSight-x.y.z-portable.zip`, unzip it to a new folder, and delete the old folder. Because your data lives under `%LOCALAPPDATA%\FinSight` (separate from the app folder), it carries over automatically.

**From-source users:**

```bat
cd finsight
git pull
.venv\Scripts\activate.bat
pip install -e ".[dev]"
finsight --selftest
```

FinSight stamps each release in `src/finsight/__init__.py` and `CHANGELOG.md`; check the [Releases page](https://github.com/kristic8998/finsight/releases) for what changed.

---

## Uninstalling

**Installer:** Windows **Settings → Apps → Installed apps → FinSight → Uninstall**, or **Start menu → FinSight → Uninstall FinSight**. The Inno Setup uninstaller removes the program files and shortcuts.

**Portable:** delete the extracted folder.

**From source:** delete the cloned folder and its `.venv`.

### Removing your data too

Uninstalling **deliberately leaves your data** (databases, backups, exported reports) in place, because it's yours. To remove it as well, delete this folder after uninstalling:

```
%LOCALAPPDATA%\FinSight
```

(Paste that path into the File Explorer address bar. If you set a custom `FINSIGHT_HOME`, delete that folder instead.)

---

## Where your data lives

| What | Location |
|---|---|
| App data, databases, backups, logs | `%LOCALAPPDATA%\FinSight` (or your `FINSIGHT_HOME`) |
| Saved DB credentials | Windows Credential Manager (via `keyring`) |
| Installed program (installer) | `%LOCALAPPDATA%\Programs\FinSight` |
| Portable program | wherever you unzipped it |

---

## Something not working?

See **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** for SmartScreen warnings, antivirus false positives, missing-DLL errors, slow first launch, and how to capture logs.
