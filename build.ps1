param([switch]$IncludeCachedModels)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'data\build-cache'
& .\setup.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\build-gpu.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$buildOriginalPath = $env:Path
try {
    # Build tools must not collect unrelated ICU / API-set DLLs from a host's PATH.
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --distpath build\package --name Transcriber --collect-data faster_whisper --collect-data ctranslate2 --collect-all onnxruntime --collect-all av --copy-metadata faster-whisper launcher.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    $env:Path = $buildOriginalPath
}
New-Item -ItemType Directory -Path 'dist\Transcriber' -Force | Out-Null
# Update executable files while preserving the user's results, models and preferences.
Copy-Item -Path 'build\package\Transcriber\*' -Destination 'dist\Transcriber' -Recurse -Force
Copy-Item -LiteralPath 'runtime' -Destination 'dist\Transcriber' -Recurse -Force
Copy-Item -LiteralPath README.md -Destination 'dist\Transcriber\README.md' -Force
if ($IncludeCachedModels -and (Test-Path -LiteralPath 'data\models')) {
    New-Item -ItemType Directory -Path 'dist\Transcriber\data\models' -Force | Out-Null
    Copy-Item -Path 'data\models\*' -Destination 'dist\Transcriber\data\models' -Recurse -Force
}
if ($IncludeCachedModels -and (Test-Path -LiteralPath 'data\models-vulkan')) {
    New-Item -ItemType Directory -Path 'dist\Transcriber\data\models-vulkan' -Force | Out-Null
    Copy-Item -Path 'data\models-vulkan\*' -Destination 'dist\Transcriber\data\models-vulkan' -Recurse -Force
}
Write-Host 'Portable app: dist\Transcriber\Transcriber.exe. Copy the entire Transcriber folder.'
