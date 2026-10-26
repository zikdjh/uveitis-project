param(
    [Parameter(Mandatory = $true)]
    [string]$AdapterDir,
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [string[]]$Tasks = @("oct_aux_4class"),
    [int]$MaxNewTokens = 32,
    [int]$ImagePixels = 65536,
    [int]$MaxSamples = 0,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root "model-training\.venv-local\Scripts\python.exe"
$evaluator = Join-Path $root "model-runtime\code\local_qwen4b_eval.py"
$adapter = if ([System.IO.Path]::IsPathRooted($AdapterDir)) {
    $AdapterDir
} else {
    Join-Path $root $AdapterDir
}
$output = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $root $OutputDir
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Local CUDA environment not found: $python"
}
if (-not (Test-Path -LiteralPath $evaluator)) {
    throw "Local evaluator not found: $evaluator"
}
if (-not (Test-Path -LiteralPath (Join-Path $adapter "adapter_config.json"))) {
    throw "Adapter not found: $adapter"
}

$env:BNB_CUDA_VERSION = "128"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_OFFLINE = "1"

$arguments = @(
    $evaluator,
    "--adapter-dir", $adapter,
    "--output-dir", $output,
    "--max-new-tokens", "$MaxNewTokens",
    "--image-pixels", "$ImagePixels"
)
foreach ($task in $Tasks) {
    $arguments += "--task"
    $arguments += $task
}
if ($MaxSamples -gt 0) {
    $arguments += "--max-samples"
    $arguments += "$MaxSamples"
}
if ($Overwrite) {
    $arguments += "--overwrite"
}

Push-Location $root
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Local evaluation failed: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
