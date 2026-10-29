param(
    [string]$ModalExe = "$PSScriptRoot\..\..\.venv-modal\Scripts\modal.exe",
    [string]$Staging = "$PSScriptRoot\..\..\datasets\training",
    [string]$Volume = "uveitis-data"
)

$ErrorActionPreference = "Stop"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path -LiteralPath $ModalExe)) {
    throw "Modal CLI not found: $ModalExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $Staging "manifest.csv"))) {
    throw "Training subset missing: $Staging"
}

$datasets = @(
    "01_uveitis_oct",
    "02_toxofundus",
    "03_eye_five_class",
    "04_odir5k",
    "06_rfmid2",
    "13_zhanglab_oct"
)

foreach ($metadata in @("manifest.csv", "odir_metadata.csv", "rfmid_labels.csv", "summary.json")) {
    $local = Join-Path $Staging $metadata
    & $ModalExe volume put --force $Volume $local "data/$metadata"
    if ($LASTEXITCODE -ne 0) {
        throw "Metadata upload failed: $metadata"
    }
}

foreach ($dataset in $datasets) {
    $local = Join-Path $Staging "data\$dataset"
    $remote = "data/data/$dataset"
    Write-Host "Uploading $dataset"
    & $ModalExe volume put --force $Volume $local $remote
    if ($LASTEXITCODE -ne 0) {
        throw "Dataset upload failed: $dataset"
    }
}

& $ModalExe volume ls $Volume "data/data"
if ($LASTEXITCODE -ne 0) {
    throw "Volume listing failed"
}

Write-Host "Training data upload complete."
