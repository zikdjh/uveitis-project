"""Check the pinned runtime can load the persisted Qwen3.5-4B processor."""

from __future__ import annotations

import json
from pathlib import Path

import modal

from modal_volumes import MODELS_VOLUME_NAME, QWEN4B_SUBDIR, models_volume


APP_NAME = "uveitis-transformers-probe"
MODEL_PATH = f"/models/{QWEN4B_SUBDIR}"
TRANSFORMERS_COMMIT = "50e35cc0ca18ec19b80653690de553e6decf74f5"
PEFT_COMMIT = "7d6315ae910bf62b6044a7ca917bccf5881f5e43"

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.8.0",
        "torchvision==0.23.0",
        f"transformers @ git+https://github.com/huggingface/transformers.git@{TRANSFORMERS_COMMIT}",
        "accelerate==1.10.1",
        f"peft @ git+https://github.com/huggingface/peft.git@{PEFT_COMMIT}",
        "bitsandbytes==0.47.0",
        "Pillow==11.3.0",
        "sentencepiece==0.2.1",
        "numpy==1.26.4",
    )
    .add_local_file(
        Path(__file__).with_name("modal_volumes.py"),
        remote_path="/root/modal_volumes.py",
        copy=True,
    )
)


@app.function(
    image=image,
    volumes={"/models": models_volume},
    timeout=15 * 60,
)
def probe() -> str:
    import accelerate
    import bitsandbytes
    import peft
    import torch
    import transformers
    from transformers import AutoConfig, AutoModelForImageTextToText, AutoProcessor

    config = AutoConfig.from_pretrained(MODEL_PATH, local_files_only=True)
    processor = AutoProcessor.from_pretrained(MODEL_PATH, local_files_only=True)
    model_classes = [
        name
        for name in dir(transformers)
        if "Qwen3_5" in name or "Qwen3VL" in name
    ]
    try:
        can_build_auto_model_class = bool(
            AutoModelForImageTextToText._model_mapping.get(type(config), None)
        )
        mapping_error = ""
    except Exception as exc:
        can_build_auto_model_class = False
        mapping_error = f"{type(exc).__name__}: {exc}"

    return json.dumps(
        {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "accelerate": accelerate.__version__,
            "peft": peft.__version__,
            "bitsandbytes": bitsandbytes.__version__,
            "cuda_available": torch.cuda.is_available(),
            "volume": MODELS_VOLUME_NAME,
            "model_path": MODEL_PATH,
            "model_type": config.model_type,
            "architectures": config.architectures,
            "auto_model_class": (
                f"{AutoModelForImageTextToText.__module__}."
                f"{AutoModelForImageTextToText.__name__}"
            ),
            "processor_class": (
                f"{processor.__class__.__module__}."
                f"{processor.__class__.__name__}"
            ),
            "can_build_auto_model_class": can_build_auto_model_class,
            "auto_model_mapping_error": mapping_error,
            "qwen_classes": model_classes,
        }
        ,
        indent=2,
        ensure_ascii=False,
    )


@app.local_entrypoint()
def main() -> None:
    print(probe.remote())
