# PyInstaller spec — one-folder build (faster startup, antivirus-friendlier).
# Build with scripts\build_windows.bat on a Windows machine.
import customtkinter
from pathlib import Path

ctk_path = Path(customtkinter.__file__).parent

a = Analysis(
    ["src/finsight/selftest.py"],
    pathex=["src"],
    datas=[(str(ctk_path), "customtkinter")],  # CTk ships theme JSON assets
    hiddenimports=[
        "sklearn.utils._typedefs",
        "sklearn.neighbors._partition_nodes",
        "matplotlib.backends.backend_tkagg",
        "keyring.backends.Windows",
    ],
    excludes=["pytest", "black", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FinSight",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="FinSight")
