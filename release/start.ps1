Set-Location $PSScriptRoot

Write-Host "`n  ####################################" -ForegroundColor DarkYellow
Write-Host "  #                                  #" -ForegroundColor DarkYellow
Write-Host "  #     🍺 云雾酒馆 · 正在开门      #" -ForegroundColor DarkYellow
Write-Host "  #                                  #" -ForegroundColor DarkYellow
Write-Host "  ####################################`n" -ForegroundColor DarkYellow

$env:PYTHONIOENCODING = "utf-8"
$env:AI_API_KEY = "public"
$env:AI_API_URL = "https://opencode.ai/zen/v1/chat/completions"

Write-Host "  AI: opencode.ai/zen (free)" -ForegroundColor Cyan
Write-Host "  Key: public" -ForegroundColor Cyan
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
    } else {
        Write-Host "  ❌ 未找到可执行文件" -ForegroundColor Red
        Write-Host "  请确保 tavern.exe 或 云雾酒馆.exe 存在于当前目录" -ForegroundColor Yellow
    }
}

Read-Host "`n按 Enter 关闭..."