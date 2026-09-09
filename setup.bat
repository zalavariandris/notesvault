@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
    echo Install uv, then run setup.bat again. See README.md for manual setup.
    exit /b 1
)
where git >nul 2>nul
if errorlevel 1 (
    echo Install Git and add it to PATH, then run setup.bat again.
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    uv venv --python 3.12
    if errorlevel 1 exit /b 1
)
uv pip install --python ".venv\Scripts\python.exe" -e ".[dev]"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" launcher.py --check
if errorlevel 1 exit /b 1
echo Setup complete. Run .venv\Scripts\python.exe launcher.py
