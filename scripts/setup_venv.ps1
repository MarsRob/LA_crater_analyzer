param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if (-not $Python) {
    $SpyderPython = Join-Path $env:LOCALAPPDATA "spyder-6\envs\spyder-runtime\python.exe"
    if (Test-Path $SpyderPython) {
        $Python = $SpyderPython
    }
    else {
        $Python = "python"
    }
}

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Virtual environment ready. Run: .\.venv\Scripts\Activate.ps1"
