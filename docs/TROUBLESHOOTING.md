# FinSight — Troubleshooting

Fixes for the problems people actually hit, grouped by when they happen. If none of these help, [open an issue](https://github.com/kristic8998/finsight/issues) with the log file described at the bottom.

---

## Installing / first launch

### "Windows protected your PC" (SmartScreen)
Expected. The installer and exe aren't code-signed, so SmartScreen warns on first run. Click **More info → Run anyway**. It appears once per machine.

### Antivirus quarantines or deletes `FinSight.exe`
A known false positive for PyInstaller apps (the bundled Python bootloader trips heuristic scanners). It is not malware. Options: restore the file from quarantine and add an exclusion for the FinSight folder, or use the **portable** build from a trusted location. If you build it yourself, the exe is exactly what you compiled.

### The app doesn't start / window flashes and closes
1. Make sure you extracted the **entire** portable folder, not just `FinSight.exe`. The exe needs its sibling `_internal\` folder — moving the exe out breaks it.
2. Confirm you're on 64-bit Windows 10/11.
3. Capture the error: open a terminal in the app folder and run the exe from there so the message stays visible:
   ```bat
   cd path\to\FinSight
   FinSight.exe
   ```
4. Check the log (see [Logs](#collecting-logs-for-a-bug-report)).

### "VCRUNTIME140.dll is missing" or a similar DLL error
Install the **Microsoft Visual C++ Redistributable (x64)** from Microsoft, then relaunch. Some minimal/older Windows images lack it; numpy/pandas need it.

### First launch is slow (10–30 seconds)
Normal for a one-folder PyInstaller app the first time — Windows is scanning the bundle and Python is importing pandas/scikit-learn/matplotlib. Subsequent launches are much faster. On a cold machine with an aggressive antivirus, the first scan dominates; add a folder exclusion if it's painful.

---

## Building from source

### `python` is not recognized
Python isn't on your PATH. Reinstall from [python.org](https://www.python.org/downloads/windows/) and tick **"Add python.exe to PATH"** on the first screen, then open a **new** terminal.

### `pip install -e .` fails to build a dependency
Upgrade pip first (`python -m pip install --upgrade pip`). Ensure you're on 64-bit Python 3.10–3.12; very new or 32-bit interpreters may lack prebuilt wheels for numpy/scikit-learn and will try (and fail) to compile from source.

### Wrong Python got used / packages "missing" after install
You're outside the virtual environment. Re-activate it — your prompt should show `(.venv)`:
```bat
.venv\Scripts\activate.bat
```

---

## Building the executable (PyInstaller)

### PyInstaller produced a Mac/Linux binary, not a `.exe`
PyInstaller does not cross-compile. Build on a **Windows** machine to get a Windows `.exe`. There is no workaround for this — it is a PyInstaller design constraint, not a bug.

### The built exe launches but a screen errors with `ModuleNotFoundError`
A dependency wasn't detected by PyInstaller's static analysis. Add it to `hiddenimports` in `FinSight.spec` and rebuild. The spec already lists the known ones (`sklearn.utils._typedefs`, `sklearn.neighbors._partition_nodes`, `matplotlib.backends.backend_tkagg`, `keyring.backends.Windows`); add the missing module name from the traceback.

### The built exe can't find CustomTkinter theme files
CustomTkinter ships JSON theme assets that must be bundled as data. The spec already does this via `datas=[(customtkinter_path, "customtkinter")]`. If you edited the spec, make sure that line is intact.

### Inno Setup: "file not found: dist\FinSight\FinSight.exe"
Run `scripts\build_windows.bat` **before** compiling `installer\finsight.iss`. The installer packages the PyInstaller output, so the build has to exist first.

---

## Running the app

### A data page shows an error or empty result
Click **↻ Refresh**. If it persists, run the self-test from a source install to localise the failing subsystem:
```bat
finsight --selftest
```
Every line should read `OK`. A `FAIL` line names the subsystem and prints a traceback.

### "Database is locked" or a connection won't open
Close any other program holding the same SQLite file (including a second FinSight window). FinSight releases its own handles on exit; if a crash left one open, restart the app.

### Saved connection can't authenticate
Credentials live in the **Windows Credential Manager**. If you changed your Windows password recently or moved machines, re-enter the credentials in **Settings → Connections**. Copying the app to a new PC does **not** copy Credential Manager entries.

### Charts look wrong or the window is tiny on a high-DPI display
Toggle the theme (**Ctrl+D**) to force a repaint, or resize the window once. On mixed-DPI multi-monitor setups, move the window to your primary display and relaunch.

### It feels slow on an integrated-graphics laptop
Expected ceilings on 16 GB / integrated GPU: keep on-screen SQL results modest (the 50,000-row cap protects you), and let analytics finish — forecasting/segmentation run on CPU. Close other heavy apps if pandas operations feel sluggish.

---

## Updating

### After updating, my settings/data are gone
They shouldn't be — data lives in `%LOCALAPPDATA%\FinSight`, separate from the program. If it looks empty, you may have set a `FINSIGHT_HOME` variable in one launch context but not another. Check whether `FINSIGHT_HOME` is set (`echo %FINSIGHT_HOME%`) and keep it consistent.

### Installer won't upgrade / says already installed
Run the new `FinSight-Setup-x.y.z.exe`; it upgrades in place (same `AppId`). If it refuses, uninstall from **Settings → Apps** first, then install the new one — your data is preserved.

---

## Uninstalling leftovers

Uninstalling intentionally leaves your data. To fully remove FinSight including data, uninstall the program, then delete `%LOCALAPPDATA%\FinSight` (paste that into the Explorer address bar). Credential Manager entries can be removed from **Control Panel → Credential Manager → Windows Credentials** (look for FinSight).

---

## Collecting logs for a bug report

FinSight writes logs under your data folder:

```
%LOCALAPPDATA%\FinSight\logs\
```

Paste that path into the File Explorer address bar, grab the most recent `.log`, and attach it to your issue along with:

- Windows version (Win+R → `winver`)
- How you installed (installer / portable / source)
- What you did right before the problem
- The self-test output (`finsight --selftest`) if you have a source install

That's usually enough to pin down the cause quickly.
