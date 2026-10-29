#!/usr/bin/env python3
r"""End-to-end regression for the analysis job failure and recovery paths.

Phase A: runtime unreachable -> Qwen branch degrades, case still completes.
Phase B: runtime too slow -> perception timeout degrades the branch.
Phase C: real runtime -> structured result and runtime metadata written back.
Phase D: runtime restart -> a new case completes after the recovered service.

Run with the backend virtual environment:

    cd model\runtime
    ..\..\backend\.venv\Scripts\python.exe scripts\run_recovery_regression.py
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
RUNTIME_ROOT = PROJECT_ROOT / "model" / "runtime"
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app  # noqa: E402
from app.schemas.case import AnalysisResult, CaseImage, CaseRead  # noqa: E402
from app.services.redis_store import MemorySessionStore  # noqa: E402

RUNTIME_PORT = 8010
SLOW_PORT = 8011
STAMP = "20261028-01"
OUTPUT_DIR = (
    PROJECT_ROOT
    / "model"
    / "training"
    / "assets"
    / "qwen3.5-4b"
    / f"runtime-recovery-local-4060-{STAMP}"
)
WORK_DIR = PROJECT_ROOT / "outputs" / f"runtime-recovery-{STAMP}"


class SlowHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        time.sleep(8.0)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args) -> None:
        pass


def pick_oct_image() -> tuple[Path, str]:
    manifest = PROJECT_ROOT / "model" / "training" / "datasets" / "training" / "manifest.csv"
    with manifest.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["task"] == "oct_uveitis_4class" and row["split"] == "test":
                path = (manifest.parent / row["image"]).resolve()
                if path.is_file():
                    return path, row["label"]
    raise RuntimeError("no test-split OCT image found in manifest")


def build_settings(**overrides):
    from app.core.config import Settings

    base = dict(
        environment="test",
        bootstrap_admin_password="regression-only",
        integration_secret_key="regression-only-integration-secret-key",
        model_mode="remote",
        qwen_judgment_enabled=True,
        rag_enabled=False,
        decision_enabled=False,
        web_search_enabled=False,
        external_summary_enabled=False,
        agent_orchestration_enabled=False,
        vector_provider="memory",
        perception_service_url=f"http://127.0.0.1:{RUNTIME_PORT}",
        perception_timeout_seconds=90.0,
    )
    base.update(overrides)
    return Settings(**base)


def build_app(case_settings, upload_dir: Path):
    return create_app(
        upload_dir=upload_dir,
        vector_dir=WORK_DIR / "vector",
        use_environment_database=False,
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
        runtime_settings=case_settings,
    )


def make_case(upload_dir: Path, image_path: Path) -> CaseRead:
    case_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())
    case_dir = upload_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    image_file = case_dir / f"{image_id}{image_path.suffix.lower()}"
    shutil.copyfile(image_path, image_file)
    now = datetime.now(UTC)
    return CaseRead(
        id=case_id,
        owner_id="doctor-regression",
        owner_name="回归医生",
        patient_age=45,
        patient_sex="M",
        complaint="右眼视物模糊两周，既往葡萄膜炎病史。",
        medical_history="双眼葡萄膜炎随访中。",
        affected_eye="OD",
        consent_confirmed=True,
        status="analyzing",
        images=[
            CaseImage(
                id=image_id,
                filename=image_path.name,
                kind="oct",
                content_type="image/jpeg",
                size_bytes=image_file.stat().st_size,
                url=f"/api/v1/cases/{case_id}/{image_id}",
            )
        ],
        analysis=AnalysisResult(
            status="queued",
            model_mode="remote",
            summary="分析任务已排队。",
            started_at=now,
        ),
        created_at=now,
        updated_at=now,
    )


def run_case(case_settings, upload_dir: Path, image_path: Path) -> dict:
    app = build_app(case_settings, upload_dir)
    case = make_case(upload_dir, image_path)
    app.state.case_store.save(case)
    job = app.state.analysis_job_service.enqueue(case.id)
    started = time.perf_counter()
    result = app.state.analysis_job_service.run_job(job.job_key)
    elapsed = time.perf_counter() - started
    stored = app.state.case_store.get(case.id)
    assert stored is not None and stored.analysis is not None
    stages = {stage.key: stage for stage in stored.analysis.stages}
    qwen = stages.get("qwen_judgment")
    return {
        "case_id": case.id,
        "job_outcome": result.outcome,
        "case_status": stored.status,
        "analysis_status": stored.analysis.status,
        "elapsed_seconds": round(elapsed, 3),
        "qwen_stage": {"status": qwen.status, "detail": qwen.detail} if qwen else None,
        "impression": stored.analysis.impression,
        "summary": stored.analysis.summary,
        "safety_flags": stored.analysis.safety_flags,
        "runtime_metadata": stored.analysis.runtime_metadata or {},
        "external_summary_used": stored.analysis.external_summary_used,
    }


def wait_health(timeout_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(
                f"http://127.0.0.1:{RUNTIME_PORT}/health", timeout=2.0
            )
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)
    raise RuntimeError(f"runtime health check failed: {last_error}")


def start_runtime() -> subprocess.Popen:
    env = os.environ.copy()
    env["MODEL_RUNTIME_UPLOAD_ROOT"] = str(WORK_DIR / "uploads")
    env["MODEL_RUNTIME_INTERNAL_TOKEN"] = "regression-internal-token"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [
            str(PROJECT_ROOT / ".venv-runtime-smoke" / "Scripts" / "python.exe"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(RUNTIME_PORT),
            "--log-level",
            "warning",
        ],
        cwd=RUNTIME_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_runtime(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    time.sleep(1.0)


def gpu_memory() -> str:
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return output.stdout.strip()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}: {exc}"


def assert_phase_a(record: dict) -> None:
    assert record["job_outcome"] == "completed", record
    assert record["case_status"] == "awaiting_review", record
    assert record["qwen_stage"]["status"] == "failed", record
    assert not record["runtime_metadata"], record
    assert any("Qwen" in flag for flag in record["safety_flags"]), record


def assert_phase_b(record: dict) -> None:
    assert record["job_outcome"] == "completed", record
    assert record["qwen_stage"]["status"] == "failed", record
    assert "Timeout" in record["qwen_stage"]["detail"], record
    assert not record["runtime_metadata"], record


def assert_phase_c(record: dict) -> None:
    assert record["job_outcome"] == "completed", record
    assert record["case_status"] == "awaiting_review", record
    assert record["qwen_stage"]["status"] == "completed", record
    meta = record["runtime_metadata"]
    assert meta.get("model"), record
    assert len(str(meta.get("adapter_sha256", ""))) == 64, record
    assert meta.get("latency_ms"), record


def main() -> int:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    upload_dir = WORK_DIR / "uploads"
    upload_dir.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path, image_label = pick_oct_image()

    evidence = {
        "generated_at": datetime.now(UTC).isoformat(),
        "host_gpu": gpu_memory(),
        "image": {"path": str(image_path), "manifest_label": image_label},
        "runtime_base_url": f"http://127.0.0.1:{RUNTIME_PORT}",
        "phases": {},
    }

    print("phase A: runtime unreachable")
    down_settings = build_settings()
    record = run_case(down_settings, upload_dir, image_path)
    assert_phase_a(record)
    evidence["phases"]["a_runtime_unreachable"] = record
    print(json.dumps(record, ensure_ascii=False, indent=2))

    print("phase B: perception timeout")
    slow_server = HTTPServer(("127.0.0.1", SLOW_PORT), SlowHandler)
    slow_thread = threading.Thread(target=slow_server.serve_forever, daemon=True)
    slow_thread.start()
    try:
        timeout_settings = build_settings(
            perception_service_url=f"http://127.0.0.1:{SLOW_PORT}",
            perception_timeout_seconds=1.5,
        )
        record = run_case(timeout_settings, upload_dir, image_path)
        assert_phase_b(record)
        evidence["phases"]["b_perception_timeout"] = record
        print(json.dumps(record, ensure_ascii=False, indent=2))
    finally:
        slow_server.shutdown()

    print("phase C: real runtime write-back")
    runtime = start_runtime()
    try:
        health = wait_health(timeout_seconds=60)
        evidence["runtime_health"] = health
        settings_c = build_settings(internal_service_token="regression-internal-token")
        record = run_case(settings_c, upload_dir, image_path)
        assert_phase_c(record)
        record["gpu_memory_after"] = gpu_memory()
        evidence["phases"]["c_real_writeback"] = record
        print(json.dumps(record, ensure_ascii=False, indent=2))

        print("phase D: runtime restart recovery")
        stop_runtime(runtime)
        runtime = start_runtime()
        wait_health(timeout_seconds=60)
        record = run_case(settings_c, upload_dir, image_path)
        assert_phase_c(record)
        evidence["phases"]["d_restart_recovery"] = record
        print(json.dumps(record, ensure_ascii=False, indent=2))
    finally:
        stop_runtime(runtime)

    evidence_path = OUTPUT_DIR / "recovery_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"evidence written: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
