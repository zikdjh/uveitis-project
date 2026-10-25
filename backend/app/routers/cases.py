from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

from app.core.security import require_role
from app.schemas.case import (
    CaseCreate,
    CaseImage,
    CaseRead,
    CaseReview,
    ImageKind,
    ReviewUpdate,
)
from app.services.analysis import AnalysisService


router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


def _get_case(request: Request, case_id: str) -> CaseRead:
    case = request.app.state.case_store.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="病例不存在")
    return case


def _run_analysis(app, case_id: str, queued) -> None:
    case = app.state.case_store.get(case_id)
    if case is None:
        return
    service: AnalysisService = app.state.analysis_service
    try:
        result = service.analyze(case, queued)
        case.status = "awaiting_review"
    except Exception as exc:
        result = queued.model_copy(
            update={
                "status": "failed",
                "completed_at": datetime.now(UTC),
                "error": str(exc),
                "safety_flags": ["分析任务失败", "必须人工复核"],
            }
        )
        case.status = "failed"
    case.analysis = result
    case.updated_at = datetime.now(UTC)
    app.state.case_store.save(case)
    sync_review_queue(app)


def sync_review_queue(app) -> None:
    cases = app.state.case_store.list(limit=200)
    app.state.redis_store.set_review_queue(
        case.id for case in cases if case.status == "awaiting_review"
    )


@router.post("", response_model=CaseRead, status_code=201)
def create_case(payload: CaseCreate, request: Request) -> CaseRead:
    require_role(request, "doctor", "admin")
    case_id = str(uuid4())
    now = datetime.now(UTC)
    case = CaseRead(
        id=case_id,
        patient_age=payload.patient_age,
        patient_sex=payload.patient_sex,
        complaint=payload.complaint,
        medical_history=payload.medical_history,
        affected_eye=payload.affected_eye,
        consent_confirmed=payload.consent_confirmed,
        status="created",
        created_at=now,
        updated_at=now,
    )
    return request.app.state.case_store.save(case)


@router.get("", response_model=list[CaseRead])
def list_cases(request: Request, limit: int = 100) -> list[CaseRead]:
    require_role(request, "doctor", "admin")
    return request.app.state.case_store.list(limit=min(max(limit, 1), 200))


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: str, request: Request) -> CaseRead:
    require_role(request, "doctor", "admin")
    return _get_case(request, case_id)


@router.post("/{case_id}/images", response_model=CaseRead)
async def upload_images(
    case_id: str,
    request: Request,
    files: Annotated[list[UploadFile], File(description="病例影像")],
    kind: Annotated[ImageKind, Form()] = "fundus",
) -> CaseRead:
    require_role(request, "doctor", "admin")
    case = _get_case(request, case_id)
    if not files:
        raise HTTPException(status_code=422, detail="请选择影像文件")

    case_upload_dir = Path(request.app.state.upload_dir) / case.id
    case_upload_dir.mkdir(parents=True, exist_ok=True)
    max_bytes: int = request.app.state.settings.max_upload_bytes
    new_images: list[CaseImage] = []

    for upload in files:
        image_id = str(uuid4())
        extension = ""
        total = 0
        target: Path | None = None
        try:
            header = await upload.read(16)
            extension = _image_extension(header)
            target = case_upload_dir / f"{image_id}{extension}"
            with target.open("wb") as output:
                chunk = header
                while chunk:
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail="单张影像不能超过 25 MB")
                    output.write(chunk)
                    chunk = await upload.read(1024 * 1024)
        except HTTPException:
            if target and target.exists():
                target.unlink()
            raise
        finally:
            await upload.close()

        new_images.append(
            CaseImage(
                id=image_id,
                filename=upload.filename or f"image{extension}",
                kind=kind,
                content_type=upload.content_type or "application/octet-stream",
                size_bytes=total,
                url=f"/api/v1/cases/{case.id}/images/{image_id}",
            )
        )

    case.images.extend(new_images)
    case.updated_at = datetime.now(UTC)
    saved = request.app.state.case_store.save(case)
    sync_review_queue(request.app)
    return saved


@router.get("/{case_id}/images/{image_id}")
def get_image(case_id: str, image_id: str, request: Request) -> FileResponse:
    require_role(request, "doctor", "admin")
    case = _get_case(request, case_id)
    image = next((item for item in case.images if item.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="影像不存在")
    matches = list((Path(request.app.state.upload_dir) / case.id).glob(f"{image_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="影像文件不存在")
    return FileResponse(matches[0], media_type=image.content_type, filename=image.filename)


@router.post("/{case_id}/analyze", response_model=CaseRead, status_code=202)
def analyze_case(
    case_id: str, request: Request, background_tasks: BackgroundTasks
) -> CaseRead:
    require_role(request, "doctor", "admin")
    case = _get_case(request, case_id)
    if case.status == "analyzing":
        raise HTTPException(status_code=409, detail="该病例正在分析")
    service: AnalysisService = request.app.state.analysis_service
    queued = service.start()
    case.status = "analyzing"
    case.analysis = queued
    case.updated_at = datetime.now(UTC)
    request.app.state.case_store.save(case)
    background_tasks.add_task(_run_analysis, request.app, case.id, queued)
    return case


@router.patch("/{case_id}/review", response_model=CaseRead)
def review_case(case_id: str, payload: ReviewUpdate, request: Request) -> CaseRead:
    require_role(request, "doctor", "admin")
    case = _get_case(request, case_id)
    if case.analysis is None or case.analysis.status != "completed":
        raise HTTPException(status_code=409, detail="分析尚未完成，暂不能复核")
    case.review = CaseReview(
        **payload.model_dump(),
        reviewed_at=datetime.now(UTC),
    )
    case.status = "reviewed"
    case.updated_at = datetime.now(UTC)
    saved = request.app.state.case_store.save(case)
    sync_review_queue(request.app)
    return saved


def _image_extension(header: bytes) -> str:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return ".tif"
    raise HTTPException(status_code=415, detail="仅支持 PNG、JPEG 或 TIFF 影像")
