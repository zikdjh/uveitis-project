#!/usr/bin/env python3
"""Read-only checks for the local Modal controller and training inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("runtime.lock.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def check(condition: bool, name: str, detail: str = "") -> dict[str, Any]:
    result = {
        "name": name,
        "ok": condition,
        "detail": detail,
    }
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""))
    return result


def verify_safetensors(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    size = path.stat().st_size
    if size < 8:
        return False, f"too small ({size})"
    with path.open("rb") as stream:
        header_bytes = struct.unpack("<Q", stream.read(8))[0]
    if header_bytes <= 0 or header_bytes >= size:
        return False, f"invalid header ({header_bytes})"
    return True, f"{size:,} bytes"


def main() -> int:
    checks: list[dict[str, Any]] = []
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    controller = lock["local_controller"]
    remote = lock["remote_training"]
    data_lock = lock["data"]
    model_lock = lock["model"]

    print(f"Project root: {ROOT}")
    controller_venv = controller["venv"]
    controller_python = Path(controller_venv)
    if not controller_python.is_absolute():
        controller_python = ROOT / controller_python
    checks.append(
        check(
            Path(sys.executable).resolve()
            == (controller_python / "Scripts/python.exe").resolve(),
            "local Python is the Modal controller venv",
            sys.executable,
        )
    )
    checks.append(
        check(
            sys.version_info[:2] == (3, 11),
            "local Python version",
            sys.version.split()[0],
        )
    )
    checks.append(
        check(
            (controller_python / "Scripts/modal.exe").is_file(),
            "Modal CLI",
            str(controller_python / "Scripts/modal.exe"),
        )
    )
    try:
        import modal

        modal_version = modal.__version__
    except Exception as exc:
        modal_version = f"import failed: {exc}"
    checks.append(
        check(
            modal_version == controller["modal"],
            "Modal client version",
            modal_version,
        )
    )

    manifest = ROOT / data_lock["manifest"]
    summary_path = ROOT / data_lock["summary"]
    checks.append(check(manifest.is_file(), "training manifest exists", str(manifest)))
    if manifest.is_file():
        manifest_hash = sha256(manifest).upper()
        checks.append(
            check(
                manifest_hash == data_lock["manifest_sha256"],
                "training manifest SHA256",
                manifest_hash,
            )
        )
        rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8-sig")))
        splits = Counter(row["split"] for row in rows)
        checks.append(
            check(
                len(rows) == data_lock["rows"],
                "training row count",
                f"{len(rows):,}",
            )
        )
        checks.append(
            check(
                dict(splits) == data_lock["splits"],
                "training split counts",
                json.dumps(dict(splits), sort_keys=True),
            )
        )
        missing = sum(
            1
            for row in rows
            if not (
                ROOT
                / "training/datasets/training"
                / row.get("image", row.get("path", ""))
            ).is_file()
        )
        checks.append(
            check(missing == 0, "training image paths exist", f"missing={missing}")
        )
    checks.append(check(summary_path.is_file(), "training summary exists", str(summary_path)))
    if summary_path.is_file():
        summary_hash = sha256(summary_path).upper()
        checks.append(
            check(
                summary_hash == data_lock["summary_sha256"],
                "training summary SHA256",
                summary_hash,
            )
        )

    model_root = ROOT / model_lock["local_root"]
    checks.append(check(model_root.is_dir(), "local model directory", str(model_root)))
    if model_root.is_dir():
        index_path = model_root / "model.safetensors.index.json"
        index_ok = index_path.is_file()
        checks.append(check(index_ok, "weight index exists", str(index_path)))
        if index_ok:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            shards = sorted(set(index["weight_map"].values()))
            checks.append(
                check(
                    len(shards) == model_lock["shards"],
                    "safetensors shard count",
                    f"{len(shards)}",
                )
            )
            for shard in shards:
                ok, detail = verify_safetensors(model_root / shard)
                checks.append(check(ok, f"weight shard {shard}", detail))
        config_path = model_root / "config.json"
        config_ok = config_path.is_file()
        checks.append(check(config_ok, "model config exists", str(config_path)))
        if config_ok:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            checks.append(
                check(
                    config.get("model_type") == model_lock["model_type"],
                    "model type",
                    str(config.get("model_type")),
                )
            )

    print("\nRemote configuration (no GPU launched):")
    print(json.dumps(remote, indent=2, ensure_ascii=False))
    failures = [item for item in checks if not item["ok"]]
    print(f"\nSummary: {len(checks) - len(failures)} passed, {len(failures)} failed")

    output = ROOT / "training/environment/doctor-report.json"
    output.write_text(
        json.dumps({"checks": checks, "failures": failures}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Report: {output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
