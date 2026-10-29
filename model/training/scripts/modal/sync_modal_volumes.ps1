param(
    [string]$ModalExe = "$PSScriptRoot\..\..\.venv-modal\Scripts\modal.exe",
    [string]$Staging = "$PSScriptRoot\..\..\datasets\training",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:NO_PROXY = "localhost,127.0.0.1,::1"

if (-not (Test-Path -LiteralPath $ModalExe)) {
    throw "Modal CLI not found: $ModalExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $Staging "manifest.csv"))) {
    throw "Training subset missing. Run build_budget_training_subset.py first."
}

$modelsRoot = Join-Path $Staging "models"
$modelsPath = Join-Path $modelsRoot "qwen\\Qwen3.5-2B"
$decisionPath = Join-Path $modelsRoot "internlm\\Intern-Decision-4B"
if (-not $SkipModels) {
    foreach ($path in @($modelsPath, $decisionPath)) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Model cache missing: $path"
        }
    }
}

& $ModalExe volume put uveitis-data $Staging data
if ($LASTEXITCODE -ne 0) { throw "Data upload failed" }

if (-not $SkipModels) {
    & $ModalExe volume put uveitis-models (Join-Path $modelsRoot "*") /
    if ($LASTEXITCODE -ne 0) { throw "Model upload failed" }
}

Write-Host "Modal volumes synchronized."
