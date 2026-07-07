Set-Location $PSScriptRoot

Write-Host "`n  ####################################" -ForegroundColor DarkYellow
Write-Host "  #                                  #" -ForegroundColor DarkYellow
Write-Host "  #     🍺 云雾酒馆 · 正在开门      #" -ForegroundColor DarkYellow
Write-Host "  #                                  #" -ForegroundColor DarkYellow
Write-Host "  ####################################`n" -ForegroundColor DarkYellow

$env:PYTHONIOENCODING = "utf-8"

$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object {
        $parts = $_.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim('"', "'")
        if ($key -eq "AI_API_KEY" -or $key -eq "AI_API_URL" -or $key -eq "SECRET_KEY") {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

if ($env:AI_API_KEY) {
    Write-Host "  AI: configured (Key: ********)" -ForegroundColor Cyan
} else {
    Write-Host "  AI: not configured (edit .env to set AI_API_KEY)" -ForegroundColor Yellow
}
Write-Host ""

Start-Sleep -Seconds 1

$exePath = Join-Path $PSScriptRoot "云雾酒馆.exe"
if (Test-Path $exePath) {
    Start-Process "http://127.0.0.1:9000"
    & $exePath
} else {
    $tavernExePath = Join-Path $PSScriptRoot "tavern.exe"
    if (Test-Path $tavernExePath) {
        Start-Process "http://127.0.0.1:9000"
        & $tavernExePath
    }
}

Read-Host "`n按 Enter 关闭..."