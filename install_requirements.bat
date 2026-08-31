@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="

if exist "..\..\.venv\Scripts\python.exe" (
    set "PYTHON=..\..\.venv\Scripts\python.exe"
)

if not defined PYTHON if exist "..\..\..\python_embeded\python.exe" (
    set "PYTHON=..\..\..\python_embeded\python.exe"
)

if not defined PYTHON (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON=python"
)

if not defined PYTHON (
    echo.
    echo ERROR: No suitable Python executable found.
    echo Please install requirements manually in the Python environment used by ComfyUI:
    echo   python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
"%PYTHON%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Requirements installed successfully.
echo Restart ComfyUI completely.
pause
