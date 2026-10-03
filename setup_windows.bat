@echo off
setlocal

cd /d "%~dp0"

set "PY="

py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python --version >nul 2>nul
    if not errorlevel 1 set "PY=python"
)

if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY="%LocalAppData%\Programs\Python\Python311\python.exe""
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY="%LocalAppData%\Programs\Python\Python313\python.exe""

if not defined PY (
    echo Python 3.11+ was not found. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>nul
    if errorlevel 1 (
        echo Repairing broken virtual environment...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv.
        pause
        exit /b 1
    )
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_failed

echo Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example. Open it and paste BOT_TOKEN.
)

echo.
echo Done. In PyCharm choose interpreter:
echo %cd%\.venv\Scripts\python.exe
echo Then run main.py
pause
exit /b 0

:install_failed
echo Failed to install dependencies. Check your Internet connection and run this file again.
pause
exit /b 1
