<#
.SYNOPSIS
    Launch the DB Viewer with an SSH tunnel to an EC2 PostgreSQL instance.

.PARAMETER SshKey
    Path to the .pem SSH private key file.
    Defaults to env var EC2_SSH_KEY_PATH.

.PARAMETER Ec2Host
    EC2 public IP or hostname.
    Defaults to env var EC2_HOST.

.PARAMETER Ec2User
    SSH username on the EC2 instance.
    Defaults to env var EC2_SSH_USER, then "ubuntu".

.PARAMETER LocalPort
    Local port for the SSH tunnel. Defaults to 15432.

.PARAMETER RemotePort
    PostgreSQL port on the EC2 instance. Defaults to 5432.

.PARAMETER PgUser
    PostgreSQL username. Defaults to "root".

.PARAMETER PgPassword
    PostgreSQL password. Defaults to "example".

.PARAMETER PgDatabase
    PostgreSQL database name. Defaults to "postgres".

.EXAMPLE
    .\connect.ps1 -SshKey "~\.ssh\my-key.pem" -Ec2Host "3.14.15.92" -Ec2User "ubuntu"
#>

param(
    [string]$SshKey     = $env:EC2_SSH_KEY_PATH,
    [string]$Ec2Host    = $env:EC2_HOST,
    [string]$Ec2User    = $(if ($env:EC2_SSH_USER) { $env:EC2_SSH_USER } else { "ubuntu" }),
    [int]$LocalPort     = 15432,
    [int]$RemotePort    = 5432,
    [string]$PgUser     = "root",
    [string]$PgPassword = "example",
    [string]$PgDatabase = "postgres"
)

$ErrorActionPreference = "Stop"

if (-not $SshKey) {
    $SshKey = Read-Host "Path to SSH .pem key file"
}
if (-not (Test-Path $SshKey)) {
    Write-Error "SSH key not found: $SshKey"
    exit 1
}

if (-not $Ec2Host) {
    $Ec2Host = Read-Host "EC2 host (IP or hostname)"
}

Write-Host "Opening SSH tunnel: localhost:$LocalPort -> $Ec2Host`:$RemotePort" -ForegroundColor Cyan

$tunnelProcess = Start-Process -FilePath "ssh" -ArgumentList @(
    "-i", $SshKey,
    "-L", "${LocalPort}:localhost:${RemotePort}",
    "-N",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ExitOnForwardFailure=yes",
    "$Ec2User@$Ec2Host"
) -PassThru -NoNewWindow

Start-Sleep -Seconds 2

if ($tunnelProcess.HasExited) {
    Write-Error "SSH tunnel failed to start. Check your key, host, and network."
    exit 1
}

Write-Host "SSH tunnel running (PID: $($tunnelProcess.Id))" -ForegroundColor Green

$env:DB_VIEWER_DSN = "postgresql://${PgUser}:${PgPassword}@localhost:${LocalPort}/${PgDatabase}"
Write-Host "DSN: $env:DB_VIEWER_DSN" -ForegroundColor Cyan

try {
    Write-Host "Starting Streamlit viewer..." -ForegroundColor Cyan
    streamlit run app.py
}
finally {
    Write-Host "Shutting down SSH tunnel (PID: $($tunnelProcess.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Green
}
