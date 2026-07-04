param(
    [string]$mode = "show"
)

$versionFile = "version.json"

if (-not (Test-Path $versionFile)) {
    Write-Output "版本文件不存在"
    exit 1
}

$v = Get-Content $versionFile -Raw | ConvertFrom-Json

if ($mode -eq "major") {
    $v.major++
    $v.minor = 0
    $v.patch = 0
} elseif ($mode -eq "minor") {
    $v.minor++
    $v.patch = 0
} elseif ($mode -eq "patch") {
    $v.patch++
}

$v | ConvertTo-Json -Compress | Set-Content $versionFile -NoNewline
Write-Output "版本号已更新为: v$($v.major).$($v.minor).$($v.patch)"