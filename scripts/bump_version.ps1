param(
    [string]$mode = "show"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionFile = Join-Path $scriptDir ".." "src" "backend" "version.json"
$changelogFile = Join-Path $scriptDir ".." "src" "backend" "CHANGELOG.json"

if (-not (Test-Path $versionFile)) {
    Write-Output "版本文件不存在: $versionFile"
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
} elseif ($mode -eq "show") {
    Write-Output "v$($v.major).$($v.minor).$($v.patch)"
    exit 0
} else {
    Write-Output "未知模式: $mode. 可用模式: show, major, minor, patch"
    exit 1
}

$v | ConvertTo-Json -Depth 5 | Set-Content $versionFile -Encoding UTF8

if (Test-Path $changelogFile) {
    $cl = Get-Content $changelogFile -Raw | ConvertFrom-Json
} else {
    $cl = [PSCustomObject]@{ history = @() }
}

$newVersion = "v$($v.major).$($v.minor).$($v.patch)"
$entry = [PSCustomObject]@{
    version = $newVersion
    old_version = "v$($v.major).$($v.minor).$($v.patch + 1)"
    type = $mode
    type_desc = switch($mode) { "major" { "重大版本更新" }; "minor" { "大版本更新" }; "patch" { "小版本更新" } }
    description = ""
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

$cl.history = ,$entry + $cl.history
$cl | ConvertTo-Json -Depth 5 | Set-Content $changelogFile -Encoding UTF8

Write-Output "版本号已更新为: $newVersion"