# Fetch the CJK source fonts the localisation build needs.
#
#   pwsh -File pipeline/fetch-fonts.ps1 [-Proxy http://127.0.0.1:7897]
#
# The build subsets these down to the glyphs actually used, so the repository
# only carries the Noto Serif SC face (already present) plus the Noto Sans SC
# variable font added for ROTD2's sans family.  The variable font is instanced
# at build time to the Regular/Bold/Black weights; ``RoadOfTheDeadCN.ttf`` is
# the bundled display face and is already in ``data/fonts``.
param(
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$fonts = Join-Path $root "data\fonts"
New-Item -ItemType Directory -Force -Path $fonts | Out-Null

$common = @{}
if ($Proxy) { $common["Proxy"] = $Proxy }

$target = Join-Path $fonts "NotoSansSC-VF.ttf"
$url = "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"

if (-not (Test-Path $target) -or (Get-Item $target).Length -lt 17000000) {
    Write-Host "downloading Noto Sans SC variable font ..."
    Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing @common
}

Write-Host "fonts ready: $target ($((Get-Item $target).Length) bytes)"
