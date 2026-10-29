param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [Parameter(Mandatory = $true)]
    [int]$AllowedGpuMinutes,
    [Parameter(Mandatory = $true)]
    [switch]$BudgetConfirmed,
    [int]$TrainLimit = 900,
    [int]$MaxSteps = 30,
    [int]$ValidationLimit = 96,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = Join-Path $root "model\training\.venv-modal\Scripts\python.exe"
$modal = Join-Path $root "model\training\.venv-modal\Scripts\modal.exe"
$doctor = Join-Path $root "model\training\environment\doctor.py"
$trainer = Join-Path $root "model\training\code\training\modal_qwen4b_train.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Modal controller Python not found: $python"
}
if (-not (Test-Path -LiteralPath $modal)) {
    throw "Modal CLI not found: $modal"
}
if ($RunId -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{5,80}$") {
    throw "RunId must contain only letters, digits, dot, underscore or hyphen (6-80 characters)."
}
if ($AllowedGpuMinutes -lt 1 -or $AllowedGpuMinutes -gt 120) {
    throw "AllowedGpuMinutes must be between 1 and 120."
}
if (-not $BudgetConfirmed) {
    throw "Budget must be checked in the Modal console first; rerun with -BudgetConfirmed."
}
if ($TrainLimit -lt 1 -or $TrainLimit -gt 20000) {
    throw "TrainLimit is outside the approved safety range."
}
if ($MaxSteps -lt 1 -or $MaxSteps -gt 2000) {
    throw "MaxSteps is outside the approved safety range."
}

Push-Location $root
try {
    & $python $doctor
    if ($LASTEXITCODE -ne 0) {
        throw "Environment doctor failed; training was not started."
    }

    $env:UV_RUN_ID = $RunId
    $env:UV_TRAIN_LIMIT = "$TrainLimit"
    $env:UV_MAX_STEPS = "$MaxSteps"
    $env:UV_MAX_MINUTES = "$AllowedGpuMinutes"
    $env:UV_VALIDATION_LIMIT = "$ValidationLimit"
    $env:UV_RUN_KIND = "approved-short-run"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Write-Host "Preparing run: $RunId"
    Write-Host "GPU wall-clock cap: $AllowedGpuMinutes minutes"
    Write-Host "Training sample cap: $TrainLimit"
    Write-Host "Maximum optimizer steps: $MaxSteps"
    if ($DryRun) {
        Write-Host "Dry run only; GPU was not started."
        return
    }

    & $modal run $trainer
    if ($LASTEXITCODE -ne 0) {
        throw "Modal training command failed: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
