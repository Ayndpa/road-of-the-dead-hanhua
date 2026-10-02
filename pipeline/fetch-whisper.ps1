# Fetch and build whisper.cpp with the Vulkan backend (AMD on Windows), all from
# China mirrors, and download a ggml model from hf-mirror.
#
#   pwsh -File pipeline/fetch-whisper.ps1
#   pwsh -File pipeline/fetch-whisper.ps1 -Model large-v3-turbo -SkipModel
#
# What it does:
#   1. installs cmake + ninja into tools/buildenv from the Tsinghua PyPI mirror
#   2. assembles a minimal Vulkan "SDK" (headers + loader + glslc) in tools/vksdk
#      from TUNA's conda-forge packages (no LunarG SDK download)
#   3. clones whisper.cpp via a GitHub proxy and builds whisper-cli with
#      -DGGML_VULKAN=ON using the VS Build Tools toolchain
#   4. downloads ggml-<Model>.bin from hf-mirror.com
#
# Everything lands under tools/ (gitignored), so the repo stays clean.
param(
    [string]$Proxy = "",
    [string]$Version = "v1.7.5",
    [string]$Model = "large-v3",
    [switch]$SkipBuild,
    [switch]$SkipModel,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

# --- domestic mirrors ---------------------------------------------------
$PyIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"
$CondaForge = "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/win-64"
$GitProxy = "https://ghfast.top"            # fallback: https://gh-proxy.com
$HfMirror = "https://hf-mirror.com"

# --- pinned conda-forge win-64 packages providing the Vulkan bits -------
$VkPackages = @(
    "shaderc-2026.4-hef10606_0.conda",                          # glslc.exe + shaderc.dll
    "glslang-16.6.0-h8fa7867_0.conda",                          # glslangValidator (shaderc dep)
    "spirv-tools-2026.3-h49e36cd_1.conda",                      # SPIRV-Tools*.dll (shaderc dep)
    "libvulkan-headers-1.4.357.0-h477610d_1.conda",             # vulkan/*.h
    "spirv-headers-1.4.350.1-h49e36cd_0.conda",                 # spirv + CMake config
    "libvulkan-loader-1.4.357.0-h477610d_2.conda"               # vulkan-1.lib/.dll
)

$src = Join-Path $tools "whisper.cpp"
$vksdk = Join-Path $tools "vksdk"
$whisperExe = Join-Path $src "build\bin\whisper-cli.exe"

function Invoke-Download([string]$Url, [string]$Out) {
    if ((Test-Path $Out) -and -not $Force) { return }
    Write-Host "  downloading $(Split-Path -Leaf $Out) ..."
    & curl.exe -L --fail --retry 3 --retry-delay 2 -C - -o $Out $Url
    if ($LASTEXITCODE -ne 0) { throw "download failed: $Url" }
}

function Expand-Conda([string]$CondaFile, [string]$Dest) {
    $tmp = Join-Path $env:TEMP ("conda_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        Expand-Archive -LiteralPath $CondaFile -DestinationPath $tmp -Force
        $pkg = Get-ChildItem $tmp -Filter "pkg-*.tar.zst" | Select-Object -First 1
        if (-not $pkg) { throw "no pkg-*.tar.zst inside $CondaFile" }
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        & tar.exe -xf $pkg.FullName -C $Dest
        if ($LASTEXITCODE -ne 0) { throw "tar failed for $($pkg.Name)" }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Copy-Into([string]$From, [string]$To) {
    if (-not (Test-Path $From)) { throw "missing $From" }
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    Copy-Item -Path (Join-Path $From "*") -Destination $To -Recurse -Force
}

# --- 1. cmake + ninja from the Tsinghua PyPI mirror ---------------------
function Get-BuildTools {
    $buildenv = Join-Path $tools "buildenv"
    $py = Join-Path $buildenv "Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Write-Host "== creating build env (cmake + ninja from TUNA PyPI)"
        & uv venv $buildenv
        & uv pip install --python $py --index-url $PyIndex cmake ninja
        if ($LASTEXITCODE -ne 0) { throw "uv pip install cmake/ninja failed" }
    }
    $cmakeDir = (& $py -c "import cmake,os;print(cmake.CMAKE_BIN_DIR)").Trim()
    $ninjaDir = (& $py -c "import ninja;print(ninja.BIN_DIR)").Trim()
    if (-not (Test-Path (Join-Path $cmakeDir "cmake.exe"))) { throw "cmake.exe not found in $cmakeDir" }
    if (-not (Test-Path (Join-Path $ninjaDir "ninja.exe"))) { throw "ninja.exe not found in $ninjaDir" }
    return @{ cmake = $cmakeDir; ninja = $ninjaDir }
}

# --- 2. assemble a minimal Vulkan SDK from conda-forge -------------------
function Get-VulkanSdk {
    if ((Test-Path (Join-Path $vksdk "ready")) -and -not $Force) {
        Write-Host "== Vulkan bits already assembled"
        return
    }
    Write-Host "== assembling Vulkan bits from TUNA conda-forge -> $vksdk"
    $pkgRoot = Join-Path $tools "conda"
    New-Item -ItemType Directory -Force -Path $pkgRoot | Out-Null
    foreach ($f in $VkPackages) {
        $conda = Join-Path $pkgRoot $f
        Invoke-Download "$CondaForge/$f" $conda
        $dest = Join-Path $pkgRoot ($f -replace "\.conda$", "")
        if (-not (Test-Path (Join-Path $dest "Library")) -or $Force) {
            Expand-Conda $conda $dest
        }
    }
    # Locate each extracted package by the directory shape it carries.
    $hdrs = $loader = $spirv = $shaderc = $null
    foreach ($d in Get-ChildItem $pkgRoot -Directory) {
        if (Test-Path (Join-Path $d.FullName "Library\include\vulkan")) { $hdrs = $d.FullName }
        if (Test-Path (Join-Path $d.FullName "Library\lib\vulkan-1.lib")) { $loader = $d.FullName }
        if (Test-Path (Join-Path $d.FullName "Library\include\spirv")) { $spirv = $d.FullName }
        if (Test-Path (Join-Path $d.FullName "Library\bin\glslc.exe")) { $shaderc = $d.FullName }
    }

    if (-not $hdrs) { throw "vulkan headers not found" }
    if (-not $loader) { throw "vulkan loader not found" }
    if (-not $spirv) { throw "spirv headers not found" }
    if (-not $shaderc) { throw "glslc not found" }

    Remove-Item -Recurse -Force $vksdk -ErrorAction SilentlyContinue
    Copy-Into (Join-Path $hdrs "Library\include") (Join-Path $vksdk "Include")
    Copy-Into (Join-Path $spirv "Library\include") (Join-Path $vksdk "Include")
    Copy-Into (Join-Path $spirv "Library\share\cmake\SPIRV-Headers") (Join-Path $vksdk "share\cmake\SPIRV-Headers")
    Copy-Into (Join-Path $loader "Library\lib") (Join-Path $vksdk "Lib")
    # glslc needs its shaderc/SPIRV-Tools DLLs next to it -- copy every package's
    # Library\bin so the whole runtime set lands in one place.
    foreach ($d in Get-ChildItem $pkgRoot -Directory) {
        $b = Join-Path $d.FullName "Library\bin"
        if (Test-Path $b) { Copy-Into $b (Join-Path $vksdk "Bin") }
    }
    New-Item -ItemType File -Force -Path (Join-Path $vksdk "ready") | Out-Null
    Write-Host "   glslc: $(Test-Path (Join-Path $vksdk 'Bin\glslc.exe'))"
}

# --- 3. clone + build whisper.cpp ---------------------------------------
function Get-Vcvars {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw "vswhere.exe not found; install VS Build Tools 2022" }
    $vs = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
    $vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path $vcvars)) { throw "vcvars64.bat not found under $vs" }
    return $vcvars
}

function Build-Whisper($cmakeDir, $ninjaDir) {
    if (-not (Test-Path (Join-Path $src ".git"))) {
        Write-Host "== cloning whisper.cpp $Version via $GitProxy"
        & git clone --depth 1 --branch $Version "$GitProxy/https://github.com/ggml-org/whisper.cpp.git" $src
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   proxy clone failed, trying github directly"
            & git clone --depth 1 --branch $Version "https://github.com/ggml-org/whisper.cpp.git" $src
        }
        if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
    }
    $vcvars = Get-Vcvars
    $buildDir = Join-Path $src "build"
    $cmakeArgs = (@(
        "-S `"$src`"", "-B `"$buildDir`"", "-G Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DGGML_VULKAN=ON",
        "-DWHISPER_BUILD_TESTS=OFF",
        "-DWHISPER_BUILD_EXAMPLES=ON",
        "-DVulkan_INCLUDE_DIR=`"$vksdk\Include`"",
        "-DVulkan_LIBRARY=`"$vksdk\Lib\vulkan-1.lib`"",
        "-DVulkan_GLSLC_EXECUTABLE=`"$vksdk\Bin\glslc.exe`"",
        "-DSPIRV-Headers_DIR=`"$vksdk\share\cmake\SPIRV-Headers`""
    ) -join " ")
    $bat = Join-Path $env:TEMP "build_whisper.bat"
    $lines = @(
        "@echo off",
        "call `"$vcvars`"",
        "set `"VULKAN_SDK=$vksdk`"",
        "set `"PATH=$vksdk\Bin;$cmakeDir;$ninjaDir;%PATH%`"",
        "cmake $cmakeArgs",
        "if errorlevel 1 exit /b 1",
        "cmake --build `"$buildDir`" --config Release"
    )
    Set-Content -LiteralPath $bat -Value ($lines -join "`r`n") -Encoding ASCII
    Write-Host "== building whisper-cli (Vulkan) - this can take a while"
    & cmd /c $bat
    if ($LASTEXITCODE -ne 0) { throw "whisper.cpp build failed" }
    if (-not (Test-Path $whisperExe)) { throw "build finished but $whisperExe is missing" }
    Write-Host "   built $whisperExe"
}

# --- 4. model from hf-mirror --------------------------------------------
function Get-Model {
    $modelDir = Join-Path $src "models"
    New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
    $dest = Join-Path $modelDir "ggml-$Model.bin"
    if ((Test-Path $dest) -and -not $Force) {
        Write-Host "== model already present: $dest"
        return
    }
    Write-Host "== downloading ggml-$Model.bin from hf-mirror (~3GB for large-v3)"
    Invoke-Download "$HfMirror/ggerganov/whisper.cpp/resolve/main/ggml-$Model.bin" $dest
    Write-Host "   wrote $dest ($([math]::Round((Get-Item $dest).Length / 1GB, 2)) GB)"
}

# --- run ----------------------------------------------------------------
$bt = Get-BuildTools
if (-not $SkipBuild) {
    Get-VulkanSdk
    Build-Whisper $bt.cmake $bt.ninja
}
if (-not $SkipModel) {
    Get-Model
}
Write-Host ""
Write-Host "whisper-cli: $whisperExe"
Write-Host "model:       $(Join-Path $src ('models\ggml-' + $Model + '.bin'))"
Write-Host "run: uv run python pipeline/asr_vulkan.py --voice-only"
