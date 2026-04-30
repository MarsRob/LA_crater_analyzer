param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Virtual environment ready. Run: .\.venv\Scripts\Activate.ps1"
