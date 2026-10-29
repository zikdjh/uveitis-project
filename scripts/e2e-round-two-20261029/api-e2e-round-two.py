"""Round-two API-level end-to-end check for the uveitis assistant.

Runs the full chain without a browser: doctor login, case creation, image
upload, real-model analysis, knowledge search, doctor review, and the
admin-managed external summary integration (enabled temporarily, then
restored to its previous state).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
UPLOAD_SOURCE = Path(
    r"D:\temp\gpt\uveitis-project\backend\data\uploads"
    r"\ff09b405-3df1-4df4-bae4-7847c41aa1de"
    r"\f330c45d-9c59-4cef-a506-7893d0877788.jpg"
)

RESULTS: dict[str, object] = {}


def log(name: str, value: object) -> None:
    RESULTS[name] = value
    print(f"{name}: {json.dumps(value, ensure_ascii=False)}", flush=True)


def make_client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=120.0, trust_env=False)


def csrf_headers(client: httpx.Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("uveitis_csrf", "")}


def login(client: httpx.Client, path: str, username: str, password: str) -> object:
    response = client.post(path, json={"username": username, "password": password})
    return {
        "status": response.status_code,
        "cookies": sorted(client.cookies.keys()),
    }


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
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {"status": response.status_code, "images": len(body.get("images", []))}


def run_analysis(client: httpx.Client, case_id: str, timeout: float = 240.0) -> object:
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
    return {
        "startStatus": started.status_code,
        "jobStatus": job.get("status"),
        "attempts": job.get("attempt_count"),
        "caseStatus": case.get("status"),
        "modelMode": analysis.get("model_mode"),
        "adapterSha": (analysis.get("runtime_metadata") or {}).get("adapter_sha256", "")[:12] or None,
        "stages": stages,
    }


def main() -> int:
    doctor = make_client()
    log("doctorLogin", login(doctor, "/api/v1/auth/login", "doctor", "doctor-dev-2026"))
    log("doctorMe", doctor.get("/api/v1/auth/me").json().get("username"))

    case_id = create_case(doctor, "左眼视物模糊两周，伴轻度眼红")
    log("caseCreated", case_id)
    log("imageUpload", upload_image(doctor, case_id))
    log("analysisBaseline", run_analysis(doctor, case_id))

    search = doctor.post(
        "/api/v1/knowledge/search",
        json={"query": "前葡萄膜炎 OCT 黄斑水肿", "top_k": 3},
        headers=csrf_headers(doctor),
    )
    hits = search.json() if search.status_code == 200 else []
    log(
        "knowledgeSearch",
        {
            "status": search.status_code,
            "hits": len(hits) if isinstance(hits, list) else None,
            "topScore": hits[0].get("score") if isinstance(hits, list) and hits else None,
        },
    )

    review = doctor.patch(
        f"/api/v1/cases/{case_id}/review",
        json={
            "decision": "accepted",
            "final_impression": "左眼 OCT 未见明显活动性病变，建议随访。",
            "note": "第二轮全量测试：医生复核通过。",
            "reviewer": "示例医生",
        },
        headers=csrf_headers(doctor),
    )
    reviewed = doctor.get(f"/api/v1/cases/{case_id}").json()
    log(
        "review",
        {
            "status": review.status_code,
            "caseStatus": reviewed.get("status"),
            "reviewer": (reviewed.get("review") or {}).get("reviewer"),
        },
    )

    admin = make_client()
    log("adminLogin", login(admin, "/api/v1/auth/admin/login", "root", "root-20261025"))
    config_before = admin.get("/api/v1/integrations").json()
    log(
        "integrationConfigBefore",
        {
            "summaryEnabled": config_before.get("summary_enabled"),
            "protocol": config_before.get("summary_protocol"),
            "baseUrl": config_before.get("summary_base_url"),
            "model": config_before.get("summary_model"),
            "searchEnabled": config_before.get("web_search_enabled"),
            "revision": config_before.get("revision"),
        },
    )

    enable = admin.patch(
        "/api/v1/integrations",
        json={"summary_enabled": True, "revision": config_before.get("revision")},
        headers=csrf_headers(admin),
    )
    log("integrationEnable", {"status": enable.status_code, "revision": enable.json().get("revision") if enable.status_code == 200 else None})

    test = admin.post(
        "/api/v1/integrations/test",
        json={"kind": "summary"},
        headers=csrf_headers(admin),
    )
    log(
        "summaryConnectionTest",
        {"status": test.status_code, "body": test.json() if test.status_code == 200 else test.text[:300]},
    )

    external_case = create_case(doctor, "左眼视物模糊两周，需外部总结链路验证")
    log("externalCaseCreated", external_case)
    log("imageUploadExternal", upload_image(doctor, external_case))
    log("analysisWithExternalSummary", run_analysis(doctor, external_case, timeout=300.0))

    current = admin.get("/api/v1/integrations").json()
    restore = admin.patch(
        "/api/v1/integrations",
        json={
            "summary_enabled": config_before.get("summary_enabled", False),
            "revision": current.get("revision"),
        },
        headers=csrf_headers(admin),
    )
    log("integrationRestore", {"status": restore.status_code, "summaryEnabled": restore.json().get("summary_enabled") if restore.status_code == 200 else None})

    doctor.close()
    admin.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
