@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%CD%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [CYBERGUARD] Creating the project virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] Python 3.11 or newer is required. Install Python and run this file again.
            pause
            exit /b 1
        )
        python -m venv .venv
    )
    if errorlevel 1 (
        echo [ERROR] Could not create .venv.
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 or newer is required.
    pause
    exit /b 1
)

"%PYTHON%" -c "import joblib, numpy, sklearn" >nul 2>nul
if errorlevel 1 (
    echo [CYBERGUARD] Installing project dependencies...
    "%PYTHON%" -m pip install -e .
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check Python and network/package access.
        pause
        exit /b 1
    )
)

if not exist "models\phishing\model.joblib" (
    if exist "datasets\phishing_email.csv" (
        echo [CYBERGUARD] Training the phishing model from datasets\phishing_email.csv...
        "%PYTHON%" -m backend.cli train --csv datasets\phishing_email.csv --output models\phishing
        if errorlevel 1 (
            echo [ERROR] Phishing model training failed.
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] The phishing model and datasets\phishing_email.csv are missing.
        echo Prepare an authorized phishing dataset first. See datasets\README.md and README.md.
        echo Then run: .venv\Scripts\python.exe -m backend.cli prepare-dataset --help
        pause
        exit /b 1
    )
)

if not exist "models\login\model.joblib" (
    echo [CYBERGUARD] Creating the reproducible synthetic login model...
    "%PYTHON%" -m backend.cli evaluate-login-ml --output models\login
    if errorlevel 1 (
        echo [ERROR] Synthetic login model evaluation failed.
        pause
        exit /b 1
    )
)

echo.
echo [CYBERGUARD] Starting the local dashboard at http://127.0.0.1:8765
echo Open that address in your browser. Press Ctrl+C here to stop the server.
echo.
"%PYTHON%" -m backend.web --host 127.0.0.1 --port 8765
endlocal
