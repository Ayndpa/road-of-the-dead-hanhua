# Fetch the third-party tools the pipeline needs (not stored in git).
#
#   pwsh -File pipeline/fetch-tools.ps1 [-Proxy http://127.0.0.1:7897]
#
param(
    [string]$Proxy = "",
    [string]$FFDecVersion = "26.3.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

$common = @{}
if ($Proxy) { $common["Proxy"] = $Proxy }

$zip = Join-Path $tools "ffdec.zip"
$url = "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version$FFDecVersion/ffdec_$FFDecVersion.zip"

if (-not (Test-Path $zip)) {
    Write-Host "downloading FFDec $FFDecVersion ..."
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing @common
}

$dest = Join-Path $tools "ffdec"
if (-not (Test-Path (Join-Path $dest "ffdec-cli.jar"))) {
    Write-Host "extracting to $dest"
    Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force
}

Write-Host "FFDec ready: $(Join-Path $dest 'ffdec-cli.jar')"
