param(
    [string]$RunId = "local-4060-smoke-20261025-06",
    [int]$Steps = 3,
    [int]$ImagePixels = 65536,
    [int]$MaxLength = 256
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root "model-training\.venv-local\Scripts\python.exe"
$trainer = Join-Path $root "model-training\code\training\local_qwen4b_smoke.py"
$model = Join-Path $root "model-training\models\qwen\Qwen3.5-4B"
$manifest = Join-Path $root "model-training\datasets\training\manifest.csv"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Local CUDA environment not found: $python"
}
if (-not (Test-Path -LiteralPath $trainer)) {
    throw "Local smoke trainer not found: $trainer"
}
if (-not (Test-Path -LiteralPath $model)) {
    throw "Local Qwen3.5-4B model not found: $model"
}
if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Training manifest not found: $manifest"
}
if ($RunId -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{5,80}$") {
    throw "RunId must contain only letters, digits, dot, underscore or hyphen."
}
if ($Steps -lt 1 -or $Steps -gt 20) {
    throw "Steps must be between 1 and 20 for a local smoke run."
}
if ($ImagePixels -lt 4096 -or $ImagePixels -gt 451584) {
    throw "ImagePixels must be between 4096 and 451584."
}
if ($MaxLength -lt 128 -or $MaxLength -gt 1024) {
    throw "MaxLength must be between 128 and 1024."
}

$env:BNB_CUDA_VERSION = "128"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_OFFLINE = "1"

Push-Location $root
try {
    Write-Host "Local GPU smoke run: $RunId"
    Write-Host "Steps: $Steps; image pixels: $ImagePixels; max tokens: $MaxLength"
    & $python $trainer `
        --run-id $RunId `
        --steps $Steps `
        --image-pixels $ImagePixels `
        --max-length $MaxLength `
        --monitor-seconds 0.5
    if ($LASTEXITCODE -ne 0) {
        throw "Local smoke training failed: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
