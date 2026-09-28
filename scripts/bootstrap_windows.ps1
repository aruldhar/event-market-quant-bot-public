$ErrorActionPreference = "Stop"

Write-Host "Checking Python..."
python --version

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

Write-Host "Installing dependencies..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Running tests..."
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Write-Host "Setup verification complete."
Write-Host "Activate the environment with: .\.venv\Scripts\Activate.ps1"
