$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw 'Install .NET 10 SDK to build the Vulkan worker. The portable app does not require an installed SDK or runtime.'
}
$env:DOTNET_CLI_HOME = Join-Path $PSScriptRoot 'data\dotnet-home'
$env:NUGET_PACKAGES = Join-Path $PSScriptRoot 'data\nuget-packages'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
& dotnet publish native\GpuWorker\GpuWorker.csproj -c Release -p:RestoreLockedMode=true -o runtime\vulkan
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# The Vulkan 1.8.1 package's CPU support DLL can execute unsupported instructions
# even on an AVX2 i5-12400. Use the ABI-matching portable CPU support DLL; the
# Vulkan backend and GPU model buffers stay enabled.
Copy-Item -LiteralPath 'runtime\vulkan\runtimes\noavx\win-x64\ggml-cpu-whisper.dll' -Destination 'runtime\vulkan\runtimes\vulkan\win-x64\ggml-cpu-whisper.dll' -Force
# Ship the VC runtime beside the native worker so a separate installer is unnecessary.
$qtPath = Join-Path $PSScriptRoot '.venv\Lib\site-packages\PySide6'
$nativePath = Join-Path $PSScriptRoot 'runtime\vulkan\runtimes\vulkan\win-x64'
foreach ($name in @('msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'vcomp140.dll')) {
    $source = Join-Path $qtPath $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $nativePath -Force }
}
Copy-Item -LiteralPath 'data\nuget-packages\whisper.net\1.8.1\LICENSE' -Destination 'runtime\vulkan\WHISPER-NET-LICENSE.txt' -Force
Write-Host 'Vulkan worker ready: runtime\vulkan\GpuWorker.exe'
