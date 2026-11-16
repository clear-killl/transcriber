$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($pythonLauncher) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { & py -3 -m venv .venv }
    } elseif ($pythonCommand) {
        & python -m venv .venv
    } else {
        Write-Host 'Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/ and run start.cmd again.'
        exit 1
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& .\.venv\Scripts\python.exe -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer is required'; assert sys.maxsize > 2**32, '64-bit Python is required'"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Ready. Open start.cmd to launch Transcriber.'
