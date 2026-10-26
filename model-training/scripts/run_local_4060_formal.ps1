param(
    [string]$RunId = "local-4060-grouped-cont-20261025-01",
    [int]$Steps = 150,
    [int]$GradAccum = 4,
    [int]$ImagePixels = 65536,
    [int]$MaxLength = 256,
    [int]$ValidationGroupsPerClass = 3,
    [int]$ValidationEvery = 25,
    [int]$SaveEvery = 25,
    [int]$EarlyStopPatience = 3,
    [double]$LearningRate = 2.5e-5,
    [string]$InitAdapter = "",
    [string[]]$TaskWeights = @(),
    [switch]$Resume,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root "model-training\.venv-local\Scripts\python.exe"
$trainer = Join-Path $root "model-training\code\training\local_qwen4b_train.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Local CUDA environment not found: $python"
}
if (-not (Test-Path -LiteralPath $trainer)) {
    throw "Formal local trainer not found: $trainer"
}
if ($RunId -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{5,80}$") {
    throw "RunId must contain only letters, digits, dot, underscore or hyphen."
}
if ($Steps -lt 1 -or $Steps -gt 5000) {
    throw "Steps must be between 1 and 5000."
}
if ($GradAccum -lt 1 -or $GradAccum -gt 32) {
    throw "GradAccum must be between 1 and 32."
}
if ($ImagePixels -lt 4096 -or $ImagePixels -gt 451584) {
    throw "ImagePixels must be between 4096 and 451584."
}
if ($MaxLength -lt 128 -or $MaxLength -gt 1024) {
    throw "MaxLength must be between 128 and 1024."
}
if ($LearningRate -le 0 -or $LearningRate -gt 0.001) {
    throw "LearningRate must be greater than 0 and at most 0.001."
}
if ($EarlyStopPatience -lt 1 -or $EarlyStopPatience -gt 20) {
    throw "EarlyStopPatience must be between 1 and 20."
}

$env:BNB_CUDA_VERSION = "128"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_OFFLINE = "1"

Push-Location $root
try {
    $arguments = @(
        $trainer,
        "--run-id", $RunId,
        "--steps", "$Steps",
        "--grad-accum", "$GradAccum",
        "--image-pixels", "$ImagePixels",
        "--max-length", "$MaxLength",
        "--validation-groups-per-class", "$ValidationGroupsPerClass",
        "--validation-every", "$ValidationEvery",
        "--save-every", "$SaveEvery",
        "--early-stop-patience", "$EarlyStopPatience",
        "--learning-rate", "$LearningRate"
    )
    if ($Resume) {
        $arguments += "--resume"
    }
    if ($InitAdapter) {
        $arguments += "--init-adapter"
        $arguments += $InitAdapter
    }
    foreach ($taskWeight in $TaskWeights) {
        $arguments += "--task-weight"
        $arguments += $taskWeight
    }
    if ($DryRun) {
        $arguments += "--dry-run"
    }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Local formal training failed: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
