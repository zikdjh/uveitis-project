"""B-05 knowledge retrieval end-to-end check.

Writes one knowledge document through the admin console API, confirms the
doctor can search it, then runs a real analysis on a case whose complaint
carries the same marker and checks that the document comes back as RAG
evidence on the case.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
MARKER = "B05-KNOWLEDGE-MARKER-20261029"
FIXTURE = Path(
    r"D:\temp\gpt\uveitis-project\backend\data\uploads"
    r"\ff09b405-3df1-4df4-bae4-7847c41aa1de"
    r"\f330c45d-9c59-4cef-a506-7893d0877788.jpg"
)


def csrf(client: httpx.Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("uveitis_csrf", "")}


def main() -> int:
    report: dict[str, object] = {}
    admin = httpx.Client(base_url=BASE, timeout=60.0, trust_env=False)
    doctor = httpx.Client(base_url=BASE, timeout=180.0, trust_env=False)

    report["adminLogin"] = admin.post(
        "/api/v1/auth/admin/login",
        json={"username": "root", "password": "root-20261025"},
    ).status_code
    report["doctorLogin"] = doctor.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "doctor-dev-2026"},
    ).status_code

    before = admin.get("/api/v1/knowledge/status").json()
    document = admin.post(
        "/api/v1/knowledge/documents",
        json={
            "title": f"B-05 端到端知识条目 {MARKER}",
            "content": (
                f"检索标记 {MARKER}。葡萄膜炎继发黄斑水肿的管理要点："
                "先控制眼内炎症，再评估是否使用局部或眼内糖皮质激素；"
                "治疗前后需要 OCT 黄斑厚度随访，并排除感染性病因。"
            ),
            "source": "B-05 端到端验收合成条目",
            "category": "guideline",
        },
        headers=csrf(admin),
    )
    report["documentStatus"] = document.status_code
    doc = document.json()
    report["documentId"] = doc.get("id")

    after = admin.get("/api/v1/knowledge/status").json()
    report["indexBefore"] = {
        "documents": before.get("documents"),
        "mode": before.get("embedding_mode"),
        "ready": before.get("ready"),
    }
    report["indexAfter"] = {
        "documents": after.get("documents"),
        "mode": after.get("embedding_mode"),
        "ready": after.get("ready"),
    }

    search = doctor.post(
        "/api/v1/knowledge/search",
        json={"query": MARKER, "top_k": 3},
        headers=csrf(doctor),
    )
    hits = search.json() if search.status_code == 200 else []
    report["searchStatus"] = search.status_code
    report["searchHits"] = [
        {
            "id": item["document"]["id"],
            "score": round(item["score"], 4),
            "title": item["document"]["title"],
        }
        for item in hits
    ]
    report["searchFoundMarker"] = any(
        item["document"]["id"] == doc.get("id") for item in hits
    )

    case = doctor.post(
        "/api/v1/cases",
        json={
            "patient_age": 41,
            "patient_sex": "F",
            "complaint": f"右眼视物模糊伴黄斑水肿随访，检索标记 {MARKER}",
            "medical_history": "B-05 知识检索端到端合成记录",
            "affected_eye": "OD",
            "consent_confirmed": True,
        },
        headers=csrf(doctor),
    )
    case_id = case.json()["id"]
    report["caseId"] = case_id

    with FIXTURE.open("rb") as handle:
        upload = doctor.post(
            f"/api/v1/cases/{case_id}/images",
            files={"files": (FIXTURE.name, handle, "image/jpeg")},
            data={"kind": "oct"},
            headers=csrf(doctor),
        )
    report["uploadStatus"] = upload.status_code

    started = doctor.post(
        f"/api/v1/cases/{case_id}/analyze",
        headers=csrf(doctor),
    )
    report["analyzeStatus"] = started.status_code

    deadline = time.time() + 240.0
    job: dict[str, object] = {}
    while time.time() < deadline:
        response = doctor.get(f"/api/v1/cases/{case_id}/analysis-job")
        if response.status_code == 200 and response.json():
            job = response.json()
            if job.get("status") in {"completed", "failed"}:
                break
        time.sleep(2.0)
    report["jobStatus"] = job.get("status")

    case_detail = doctor.get(f"/api/v1/cases/{case_id}").json()
    analysis = case_detail.get("analysis") or {}
    stages = {item["key"]: item for item in analysis.get("stages", [])}
    evidence = analysis.get("evidence") or []
    report["caseStatus"] = case_detail.get("status")
    report["retrievalStage"] = {
        "status": stages.get("retrieval", {}).get("status"),
        "detail": stages.get("retrieval", {}).get("detail"),
    }
    report["analysisEvidence"] = [
        {
            "id": item.get("id"),
            "score": round(item.get("score", 0), 4),
            "snippet": (item.get("snippet") or "")[:90],
        }
        for item in evidence
    ]
    report["evidenceIncludesDocument"] = any(
        item.get("id") == doc.get("id") for item in evidence
    )

    admin.close()
    doctor.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
