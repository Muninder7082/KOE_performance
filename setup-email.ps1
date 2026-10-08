# Configure e-mail sending for the local app (Gmail or Microsoft 365 / Outlook SMTP).
# Updates backend\.env on this PC only. Restart run-local.ps1 afterwards.
#
# Run:  powershell -ExecutionPolicy Bypass -File ".\setup-email.ps1"

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "backend\.env not found. Run run-local.ps1 once first." -ForegroundColor Red
    exit 1
}

Write-Host "Send e-mails from:" -ForegroundColor Cyan
Write-Host "  1) Gmail  (needs a Gmail App Password - no IT team needed)"
Write-Host "  2) Microsoft 365 / Outlook  (IT must enable SMTP AUTH for the mailbox)"
$choice = Read-Host "Choose 1 or 2"
if ($choice -eq "2") {
    $smtpHost = "smtp.office365.com"
    $example = "monitor@koenig-solutions.com"
    $pwLabel = "Password or App Password for that mailbox"
} else {
    $smtpHost = "smtp.gmail.com"
    $example = "yourname@gmail.com"
    $pwLabel = "Gmail App Password (16 letters, spaces are fine)"
}

$user = (Read-Host "E-mail address to send from (e.g. $example)").Trim()
$secure = Read-Host $pwLabel -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if ($smtpHost -eq "smtp.gmail.com") { $password = $password -replace "\s", "" }
$fromName = Read-Host "Sender name [Website Performance Monitor]"
if (-not $fromName) { $fromName = "Website Performance Monitor" }

$settings = [ordered]@{
    "EMAIL_PROVIDER"  = "smtp"
    "SMTP_HOST"       = $smtpHost
    "SMTP_PORT"       = "587"
    "SMTP_SECURITY"   = "starttls"
    "SMTP_USERNAME"   = $user
    "SMTP_PASSWORD"   = $password
    "EMAIL_FROM"      = $user
    "EMAIL_FROM_NAME" = $fromName
}

$lines = Get-Content $envFile | Where-Object { $line = $_; -not ($settings.Keys | Where-Object { $line -like "$_=*" }) }
foreach ($k in $settings.Keys) { $lines += "$k=$($settings[$k])" }
Set-Content -Path $envFile -Value $lines -Encoding ascii

Write-Host ""
Write-Host "Saved ($smtpHost). Now:" -ForegroundColor Green
Write-Host " 1. Stop the running app (Ctrl + C) and start run-local.ps1 again."
Write-Host " 2. Settings page -> add Report / Alert e-mail recipients -> Save settings."
Write-Host " 3. Settings page -> Send Test Email."
