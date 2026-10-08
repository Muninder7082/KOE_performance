# Run the Website Performance Monitor on this PC (local testing).
# First run asks for the PageSpeed API key and admin login and saves them in backend\.env
# (that file stays on this PC: it is excluded from Git and from the Docker image).
#
# Start:  powershell -ExecutionPolicy Bypass -File ".\run-local.ps1"
# Stop:   Ctrl + C

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$envFile = Join-Path $backend ".env"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Python environment not found. Creating it (one time, a few minutes)..." -ForegroundColor Yellow
    py -3.11 -m venv (Join-Path $root ".venv")
    & $python -m pip install -r (Join-Path $backend "requirements-dev.txt")
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Host "Building the dashboard (one time)..." -ForegroundColor Yellow
    Push-Location (Join-Path $root "frontend")
    npm install --no-audit --no-fund
    npm run build
    Pop-Location
}

function New-RandomString { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ }) }

if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "First-time setup" -ForegroundColor Cyan
    $key = Read-Host "Paste your PageSpeed API key (starts with AIza)"
    $email = Read-Host "Admin login e-mail"
    do {
        $password = Read-Host "Admin password (min 10 characters)"
    } while ($password.Length -lt 10)

    $lines = @(
        "DATABASE_URL=sqlite+aiosqlite:///./local.db",
        "SECRET_KEY=$(New-RandomString)",
        "SCHEDULER_TOKEN=$(New-RandomString)",
        "PAGESPEED_API_KEY=$($key.Trim())",
        "ADMIN_EMAIL=$($email.Trim())",
        "ADMIN_PASSWORD=$password",
        "ENVIRONMENT=development",
        "COOKIE_SECURE=false",
        "TRUSTED_PROXY_HOPS=0",
        "EMAIL_PROVIDER=disabled",
        "LOCAL_STORAGE_DIR=../data",
        "STORAGE_LOCAL_IS_PERSISTENT=true",
        "FRONTEND_DIST=../frontend/dist",
        "APP_TIMEZONE=Asia/Kolkata"
    )
    Set-Content -Path $envFile -Value $lines -Encoding ascii
    Write-Host "Saved settings to backend\.env" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting... open http://localhost:7860 in your browser (Ctrl + C to stop)" -ForegroundColor Green
Start-Job -ScriptBlock { Start-Sleep -Seconds 6; Start-Process "http://localhost:7860" } | Out-Null
Set-Location $backend
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 7860 --no-use-colors
