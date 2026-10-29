#!/usr/bin/env python3
"""Validate dataset manifests and record the pre-cleanup archive verification."""

from __future__ import annotations

import argparse
import csv
import sys
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASETS = PROJECT_ROOT / "model" / "training" / "datasets"
EXTRACTED = DATASETS / "extracted"
TRAINING = DATASETS / "training"
EXTRACTED_MANIFEST = EXTRACTED / "manifests/extracted-files.csv"
LEGACY_EXTENSION = ".zip"


@dataclass(frozen=True)
class ArchiveMapping:
    archive: Path
    destination: Path
    strip_prefix: str = ""


@dataclass
class Verification:
    archives: int = 0
    entries: int = 0
    verified: int = 0
    ignored: int = 0
    missing: list[str] = field(default_factory=list)
    size_mismatches: list[str] = field(default_factory=list)
    crc_mismatches: list[str] = field(default_factory=list)


def mapping(archive: str, destination: str, prefix: str = "") -> ArchiveMapping:
    return ArchiveMapping(DATASETS / archive, EXTRACTED / destination, prefix)


ARCHIVE_MAPPINGS = [
    mapping(
        "Optical Coherence Tomography (OCT) Images of Proliferative "
        "Vitreoretinopathy, Uveitis, and Normal Eyes.zip",
        "01_uveitis_oct",
    ),
    mapping(
        "Ocular_Toxoplasmosis_Data_V3.zip",
        "02_toxofundus",
    ),
    mapping(
        "Image Dataset on Eye Diseases Classification (Uveitis, Conjunctivitis, "
        "Cataract, Eyelid) with Symptoms and SMOTE Validation.zip",
        "03_eye_five_class",
    ),
    mapping(
        "archive (1).zip",
        "03_eye_five_class",
    ),
    mapping("archive (2).zip", "04_odir5k_preprocessed"),
    mapping("archive.zip", "05_fundus_1000"),
    mapping("ADAM.zip", "07_adam"),
    mapping("AGE.zip", "08_age"),
    mapping("GOALS.zip", "09_goals"),
    mapping("PALM.zip", "10_palm"),
    mapping("REFUGE1-Multi-rater label Data.zip", "11_refuge_multirater"),
    mapping("REFUGE2.zip", "12_refuge2"),
]

def ignored_member(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return (
        not parts
        or name.endswith("/")
        or "__MACOSX" in parts
        or parts[-1] == ".DS_Store"
    )


def crc32_file(path: Path) -> int:
    checksum = 0
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def destination_for(
    member_name: str,
    destination: Path,
    strip_prefix: str,
) -> Path | None:
    name = PurePosixPath(member_name)
    prefix = PurePosixPath(strip_prefix) if strip_prefix else None
    relative = name
    if prefix and name.parts[: len(prefix.parts)] == prefix.parts:
        relative = PurePosixPath(*name.parts[len(prefix.parts) :])
    if not relative.parts:
        return None
    return destination.joinpath(*relative.parts)


def verify_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    strip_prefix: str,
    result: Verification,
    label: str,
) -> None:
    if ignored_member(info.filename):
        result.ignored += 1
        return

    result.entries += 1
    target = destination_for(info.filename, destination, strip_prefix)
    if target is None or not target.is_file():
        result.missing.append(f"{label}!{info.filename} -> {target}")
        return

    if target.stat().st_size != info.file_size:
        result.size_mismatches.append(
            f"{label}!{info.filename} -> {target} "
            f"({info.file_size} != {target.stat().st_size})"
        )
        return

    if crc32_file(target) != info.CRC:
        result.crc_mismatches.append(f"{label}!{info.filename} -> {target}")
        return

    result.verified += 1


def verify_zip(
    archive_path: Path,
    destination: Path,
    result: Verification,
    strip_prefix: str = "",
) -> None:
    before = {
        "verified": result.verified,
        "missing": len(result.missing),
        "size": len(result.size_mismatches),
        "crc": len(result.crc_mismatches),
    }
    result.archives += 1
    label = str(archive_path.relative_to(DATASETS))
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            verify_entry(
                archive,
                info,
                destination,
                strip_prefix,
                result,
                label,
            )
    print(
        f"{label}: verified={result.verified - before['verified']:,}, "
        f"missing={len(result.missing) - before['missing']:,}, "
        f"size={len(result.size_mismatches) - before['size']:,}, "
        f"crc={len(result.crc_mismatches) - before['crc']:,}"
    )


def verify_extracted_manifest(result: Verification) -> None:
    manifest = EXTRACTED_MANIFEST
    if not manifest.is_file():
        result.missing.append(f"missing manifest: {manifest}")
        return

    rows = 0
    with manifest.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            rows += 1
            if row["relative_path"].lower().endswith(LEGACY_EXTENSION):
                result.ignored += 1
                continue
            target = EXTRACTED / row["relative_path"]
            if not target.is_file():
                if len(result.missing) < 100:
                    result.missing.append(f"manifest: {target}")
                continue
            expected_size = int(row["size_bytes"])
            if target.stat().st_size != expected_size:
                if len(result.size_mismatches) < 100:
                    result.size_mismatches.append(
                        f"manifest: {target} "
                        f"({expected_size} != {target.stat().st_size})"
                    )
    print(f"extracted manifest: {rows:,} rows checked")


def verify_training_manifest(result: Verification) -> None:
    manifest = TRAINING / "manifest.csv"
    if not manifest.is_file():
        result.missing.append(f"missing manifest: {manifest}")
        return

    rows = 0
    with manifest.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        field = "image" if "image" in (reader.fieldnames or []) else "path"
        for row in reader:
            rows += 1
            target = TRAINING / row[field]
            if not target.is_file() and len(result.missing) < 100:
                result.missing.append(f"training manifest: {target}")
    print(f"training manifest: {rows:,} rows checked")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="Validate manifests after archives and the training layout were cleaned.",
    )
    args = parser.parse_args()
    if not args.manifests_only:
        print(
            "Archives were already verified and deleted. Use --manifests-only "
            "to validate the retained dataset layout.",
            file=sys.stderr,
        )
        return 2

    if not EXTRACTED.is_dir() or not TRAINING.is_dir():
        print("dataset directories are incomplete", file=sys.stderr)
        return 2

    result = Verification()
    print(f"archives: {result.archives}")
    print(f"archive members checked: {result.entries:,}")
    print(f"verified: {result.verified:,}")
    print(f"ignored metadata/directories: {result.ignored:,}")
    print(f"missing: {len(result.missing):,}")
    print(f"size mismatches: {len(result.size_mismatches):,}")
    print(f"crc mismatches: {len(result.crc_mismatches):,}")

    verify_extracted_manifest(result)
    verify_training_manifest(result)

    problems = result.missing + result.size_mismatches + result.crc_mismatches
    if problems:
        print("\nFirst problems:")
        for problem in problems[:50]:
            print(problem)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
