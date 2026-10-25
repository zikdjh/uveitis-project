"""Probe Modal runtime codecs without loading a model or a GPU."""

from __future__ import annotations

import json
import sys

import modal


app = modal.App("uveitis-codec-probe")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch==2.8.0",
    "torchvision==0.23.0",
    "Pillow==11.3.0",
)


@app.function(image=image)
def probe() -> str:
    import PIL
    import torch
    import torchvision

    return json.dumps(
        {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "pillow": PIL.__version__,
            "cuda_available": torch.cuda.is_available(),
        }
    )


@app.local_entrypoint()
def main() -> None:
    print(probe.remote())
