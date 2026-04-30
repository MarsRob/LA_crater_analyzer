@echo off
setlocal

set PYTHON=python
set SPYDER_PYTHON=%LOCALAPPDATA%\spyder-6\envs\spyder-runtime\python.exe
if exist "%SPYDER_PYTHON%" set PYTHON="%SPYDER_PYTHON%"
if not "%~1"=="" set PYTHON=%~1

%PYTHON% -m venv .venv
if errorlevel 1 exit /b %errorlevel%

.\.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b %errorlevel%

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

echo Virtual environment ready. Run: .\.venv\Scripts\activate.bat
