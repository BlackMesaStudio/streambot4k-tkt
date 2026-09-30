@echo off
setlocal
cd /d "%~dp0"

set "PY="
where pythonw.exe >nul 2>&1 && set "PY=pythonw.exe"
if not defined PY (
    where python.exe >nul 2>&1 && set "PY=python.exe"
)
if not defined PY (
    echo Python was not found in PATH. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

%PY% -c "import PySide6.QtWidgets, requests" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies ^(PySide6, requests^) ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

start "" %PY% "%~dp0loginmg.py"
exit /b 0
