$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "grafel-pycache"

Write-Host "Compiling Grafel modules..."
python -m py_compile (Join-Path $repo "grafel.py")
Get-ChildItem (Join-Path $repo "grafel_core") -Filter *.py | ForEach-Object {
    python -m py_compile $_.FullName
}
python -m py_compile (Join-Path $repo "server\\app.py")

Write-Host "Running unit tests..."
Push-Location $repo
try {
    python -m unittest discover -s tests -v
} finally {
    Pop-Location
}

Write-Host "Verification complete."
