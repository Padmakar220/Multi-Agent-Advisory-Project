@echo off
REM Setup Python virtual environment and install dependencies (Windows)

echo Setting up Python 3.11 virtual environment...

REM Check if Python 3.11 is available
python --version | findstr "3.11" >nul
if errorlevel 1 (
    echo Error: Python 3.11 is not installed
    echo Please install Python 3.11 before running this script
    exit /b 1
)

REM Create virtual environment
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt

echo.
echo Virtual environment setup complete!
echo.
echo To activate the virtual environment, run:
echo   venv\Scripts\activate.bat
echo.
echo To deactivate, run:
echo   deactivate
