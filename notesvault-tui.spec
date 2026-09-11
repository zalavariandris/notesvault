from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
# Include desktop dependencies too so the shared --check command remains usable.
for package in ("edifice", "qasync", "pyicloud", "keyring", "platformdirs", "fido2"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis(["launcher_tui.py"], pathex=["src"], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="notesvault-tui",
          console=True, debug=False, strip=False, upx=False)
