param(
    [int]$Workers = 2,
    [string]$UploadRoot = ""
)

$ErrorActionPreference = "Stop"

if ($UploadRoot) {
    $env:MODEL_RUNTIME_UPLOAD_ROOT = (Resolve-Path $UploadRoot).Path
}
if (-not $env:MODEL_RUNTIME_UPLOAD_ROOT) {
    throw "MODEL_RUNTIME_UPLOAD_ROOT is required; pass -UploadRoot or set the environment variable."
}

$workerCount = [Math]::Max(1, $Workers)
Set-Location (Join-Path $PSScriptRoot "..")
& (Resolve-Path "..\.venv-runtime-smoke\Scripts\python.exe") -m uvicorn app.main:app `
    --host 127.0.0.1 `
    --port 8010 `
    --workers $workerCount
