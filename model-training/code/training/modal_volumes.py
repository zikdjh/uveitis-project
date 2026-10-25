"""Shared Modal persistent volumes for uveitis training artifacts."""

from __future__ import annotations

import modal


DATA_VOLUME_NAME = "uveitis-data"
MODELS_VOLUME_NAME = "uveitis-models"
RUNS_VOLUME_NAME = "uveitis-runs"

data_volume = modal.Volume.from_name(DATA_VOLUME_NAME, create_if_missing=True)
models_volume = modal.Volume.from_name(MODELS_VOLUME_NAME, create_if_missing=True)
runs_volume = modal.Volume.from_name(RUNS_VOLUME_NAME, create_if_missing=True)

VOLUMES = {
    "/data": data_volume,
    "/models": models_volume,
    "/runs": runs_volume,
}

DATA_ROOT = "/data/data/data"
MANIFEST_PATH = "/data/data/manifest.csv"
QWEN_SUBDIR = "qwen/Qwen3.5-2B"
QWEN4B_SUBDIR = "qwen/Qwen3.5-4B"
DECISION_SUBDIR = "internlm/Intern-Decision-4B"
RUNS_ROOT = "/runs"

PHASE1_TASKS = (
    "oct_uveitis_4class",
    "fundus_toxo_binary",
    "eye_five_class",
    "oct_aux_4class",
)

EVAL_TASK_LIMITS = {
    "oct_uveitis_4class": 40,
    "fundus_toxo_binary": 20,
    "eye_five_class": 30,
    "oct_aux_4class": 20,
}

TASK_LABELS = {
    "oct_uveitis_4class": [
        "Intermediate+Posterior Uveitis",
        "Normal",
        "Panuveitis",
        "RRD-PVR",
    ],
    "fundus_toxo_binary": ["healthy", "toxoplasmosis"],
    "eye_five_class": [
        "Cataract",
        "Conjunctivitis",
        "Eyelid",
        "Normal",
        "Uveitis",
    ],
    "oct_aux_4class": ["CNV", "DME", "DRUSEN", "NORMAL"],
}
