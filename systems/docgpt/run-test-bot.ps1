# Run the DocGPT test bot on Windows (loads .env.test without relying on bash).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env.test")) {
    Write-Error ".env.test not found. Create it from .env.test.example first."
}

Get-Content ".env.test" | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $i = $line.IndexOf("=")
    if ($i -lt 1) { return }
    $name = $line.Substring(0, $i).Trim()
    $value = $line.Substring($i + 1).Trim()
    # Strip optional surrounding quotes
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

Write-Host "Starting isolated test databases..."
docker compose -f docker-compose.test.yml up -d

Write-Host "Running test bot with .env.test configuration..."
uv run python main.py
