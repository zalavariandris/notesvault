from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for package in ("edifice", "qasync", "pyicloud", "keyring", "platformdirs", "fido2"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis(["launcher.py"], pathex=["src"], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="notesvault-gui",
          console=False, debug=False, strip=False, upx=False)
