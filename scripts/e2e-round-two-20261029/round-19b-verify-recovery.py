"""Verify the B-02 recovery half from the API side (no browser).

Logs in as the doctor account, reads the case and its analysis job, and prints
the Qwen stage status plus the runtime metadata written back by the runtime
service.
"""

from __future__ import annotations

import json

import httpx

BASE = "http://127.0.0.1:8000"
CASE_ID = "47bd1e4c-39c9-48d0-9980-bbbbb4b0e451"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0, trust_env=False) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "doctor", "password": "doctor-dev-2026"},
        )
        case = client.get(f"/api/v1/cases/{CASE_ID}").json()
        job = client.get(f"/api/v1/cases/{CASE_ID}/analysis-job").json()

    analysis = case.get("analysis") or {}
    stages = {item["key"]: item["status"] for item in analysis.get("stages", [])}
    metadata = analysis.get("runtime_metadata") or {}
    print(
        json.dumps(
            {
                "loginStatus": login.status_code,
                "caseStatus": case.get("status"),
                "analysisStatus": analysis.get("status"),
                "modelMode": analysis.get("model_mode"),
                "adapterSha256": metadata.get("adapter_sha256"),
                "modelName": metadata.get("model_name"),
                "latencyMs": metadata.get("latency_ms"),
                "peakReservedGib": metadata.get("peak_reserved_gib"),
                "qwenStatus": stages.get("qwen_judgment"),
                "jobStatus": job.get("status"),
                "attempt": job.get("attempt_count"),
                "maxAttempts": job.get("max_attempts"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
