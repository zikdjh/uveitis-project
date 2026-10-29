"""Round-two external integration check: enable summary API, test it, run an
analysis that reaches the external summary branch, then restore the config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
ADMIN_API = "/api/v1/admin/integrations"
UPLOAD_SOURCE = Path(
    r"D:\temp\gpt\uveitis-project\backend\data\uploads"
    r"\ff09b405-3df1-4df4-bae4-7847c41aa1de"
    r"\f330c45d-9c59-4cef-a506-7893d0877788.jpg"
)


def log(name: str, value: object) -> None:
    print(f"{name}: {json.dumps(value, ensure_ascii=False)}", flush=True)


def csrf_headers(client: httpx.Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("uveitis_csrf", "")}


def create_case(client: httpx.Client, complaint: str) -> str:
    response = client.post(
        "/api/v1/cases",
        json={
            "patient_age": 34,
            "patient_sex": "F",
            "complaint": complaint,
            "medical_history": "否认既往葡萄膜炎病史",
            "affected_eye": "OS",
            "consent_confirmed": True,
        },
        headers=csrf_headers(client),
    )
    response.raise_for_status()
    return response.json()["id"]


def upload_image(client: httpx.Client, case_id: str) -> object:
    with UPLOAD_SOURCE.open("rb") as handle:
        response = client.post(
            f"/api/v1/cases/{case_id}/images",
            files={"files": (UPLOAD_SOURCE.name, handle, "image/jpeg")},
            data={"kind": "oct"},
            headers=csrf_headers(client),
        )
    return {"status": response.status_code}


def run_analysis(client: httpx.Client, case_id: str, timeout: float = 300.0) -> object:
    import time

    started = client.post(f"/api/v1/cases/{case_id}/analyze", headers=csrf_headers(client))
    deadline = time.time() + timeout
    job: dict[str, object] = {}
    while time.time() < deadline:
        response = client.get(f"/api/v1/cases/{case_id}/analysis-job")
        if response.status_code == 200 and response.json():
            job = response.json()
            if job.get("status") in {"completed", "failed"}:
                break
        time.sleep(2.0)
    case = client.get(f"/api/v1/cases/{case_id}").json()
    analysis = case.get("analysis") or {}
    stages = {item["key"]: item["status"] for item in analysis.get("stages", [])}
    summary_stage = next(
        (item for item in analysis.get("stages", []) if item["key"] == "external_summary"),
        {},
    )
    return {
        "startStatus": started.status_code,
        "jobStatus": job.get("status"),
        "caseStatus": case.get("status"),
        "modelMode": analysis.get("model_mode"),
        "stages": stages,
        "externalSummaryDetail": (summary_stage.get("detail") or "")[:160],
    }


def main() -> int:
    admin = httpx.Client(base_url=BASE, timeout=120.0, trust_env=False)
    doctor = httpx.Client(base_url=BASE, timeout=300.0, trust_env=False)

    doctor.post("/api/v1/auth/login", json={"username": "doctor", "password": "doctor-dev-2026"})
    admin.post("/api/v1/auth/admin/login", json={"username": "root", "password": "root-20261025"})

    before = admin.get(ADMIN_API).json()
    log("configBefore", {k: before.get(k) for k in ("summary_enabled", "summary_protocol", "summary_base_url", "summary_model", "web_search_enabled", "revision")})

    enable = admin.patch(ADMIN_API, json={"summary_enabled": True, "revision": before.get("revision")}, headers=csrf_headers(admin))
    log("enableSummary", {"status": enable.status_code})

    test = admin.post(f"{ADMIN_API}/test", json={"kind": "summary"}, headers=csrf_headers(admin))
    log("summaryTest", {"status": test.status_code, "body": test.json() if test.status_code == 200 else test.text[:200]})

    batch = admin.post(f"{ADMIN_API}/test-search-batch", json={}, headers=csrf_headers(admin))
    log("searchBatchTest", {"status": batch.status_code, "body": batch.json() if batch.status_code == 200 else batch.text[:200]})

    case_id = create_case(doctor, "左眼视物模糊两周，外部总结链路验证")
    log("caseCreated", case_id)
    log("imageUpload", upload_image(doctor, case_id))
    log("analysisWithSummary", run_analysis(doctor, case_id))

    current = admin.get(ADMIN_API).json()
    restore = admin.patch(
        ADMIN_API,
        json={"summary_enabled": bool(before.get("summary_enabled")), "revision": current.get("revision")},
        headers=csrf_headers(admin),
    )
    log("restore", {"status": restore.status_code, "summaryEnabled": restore.json().get("summary_enabled") if restore.status_code == 200 else None})

    admin.close()
    doctor.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
