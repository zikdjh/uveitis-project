from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

from app.core.security import require_permission
from app.schemas.case import (
    CaseCreate,
    CaseImage,
    CaseListPage,
    CaseRead,
    CaseReview,
    ImageKind,
    ReviewUpdate,
)
from app.schemas.auth import Permission, UserRead
from app.services.analysis import AnalysisService


router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


def _get_case(request: Request, case_id: str, actor: UserRead) -> CaseRead:
    case = request.app.state.case_store.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="病例不存在")
    if actor.role != "admin" and case.owner_id != actor.id:
        # Do not reveal whether another doctor's case exists.
        raise HTTPException(status_code=404, detail="病例不存在")
    return case


def _owner_scope(actor: UserRead) -> str | None:
    return None if actor.role == "admin" else actor.id


def _require_clinical_actor(actor: UserRead) -> None:
    if actor.role != "doctor":
        raise HTTPException(
            status_code=403,
            detail="管理员仅可审计病例，不能修改临床记录",
        )


def _date_bounds(from_date: str | None, to_date: str | None):
    try:
        start = (
            datetime.combine(datetime.fromisoformat(from_date).date(), time.min, UTC)
            if from_date
            else None
        )
        end = (
            datetime.combine(
                datetime.fromisoformat(to_date).date() + timedelta(days=1),
                time.min,
                UTC,
            )
            if to_date
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD") from exc
    if start and end and start >= end:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    return start, end


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
    cases = app.state.case_store.list(status="awaiting_review", limit=10_000)
    app.state.redis_store.set_review_queue(
        case.id for case in cases
    )


@router.post("", response_model=CaseRead, status_code=201)
def create_case(payload: CaseCreate, request: Request) -> CaseRead:
    actor = require_permission(request, Permission.CASE_WRITE)
    _require_clinical_actor(actor)
    case_id = str(uuid4())
    now = datetime.now(UTC)
    case = CaseRead(
        id=case_id,
        owner_id=actor.id,
        owner_name=actor.display_name,
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


@router.get("", response_model=CaseListPage)
def list_cases(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=100),
    status: str | None = Query(default=None, max_length=30),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> CaseListPage:
    actor = require_permission(request, Permission.CASE_READ)
    if status and status not in {
        "created",
        "analyzing",
        "awaiting_review",
        "reviewed",
        "failed",
    }:
        raise HTTPException(status_code=422, detail="不支持的病例状态")
    from_at, to_at = _date_bounds(from_date, to_date)
    store = request.app.state.case_store
    scope = _owner_scope(actor)
    total = store.count(owner_id=scope, status=status, from_at=from_at, to_at=to_at)
    items = store.list(
        owner_id=scope,
        status=status,
        from_at=from_at,
        to_at=to_at,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    visible_items = []
    for item in items:
        if not item.owner_name:
            owner = request.app.state.user_store.get(item.owner_id)
            if owner is not None:
                item = item.model_copy(update={"owner_name": owner.display_name})
        visible_items.append(item)
    return CaseListPage(items=visible_items, total=total, page=page, page_size=page_size)


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: str, request: Request) -> CaseRead:
    actor = require_permission(request, Permission.CASE_READ)
    return _get_case(request, case_id, actor)


@router.post("/{case_id}/images", response_model=CaseRead)
async def upload_images(
    case_id: str,
    request: Request,
    files: Annotated[list[UploadFile], File(description="病例影像")],
    kind: Annotated[ImageKind, Form()] = "fundus",
) -> CaseRead:
    actor = require_permission(request, Permission.CASE_WRITE)
    _require_clinical_actor(actor)
    case = _get_case(request, case_id, actor)
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
    actor = require_permission(request, Permission.CASE_READ)
    case = _get_case(request, case_id, actor)
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
    actor = require_permission(request, Permission.CASE_WRITE)
    _require_clinical_actor(actor)
    case = _get_case(request, case_id, actor)
    if case.status == "analyzing":
        raise HTTPException(status_code=409, detail="该病例正在分析")
    service: AnalysisService = request.app.state.analysis_service
    queued = service.start()
    case.status = "analyzing"
    case.analysis = queued
    case.updated_at = datetime.now(UTC)
    request.app.state.case_store.save(case)
    job = request.app.state.analysis_job_service.enqueue(case.id)
    background_tasks.add_task(
        request.app.state.analysis_job_service.run_job,
        job.job_key,
    )
    return case


@router.patch("/{case_id}/review", response_model=CaseRead)
def review_case(case_id: str, payload: ReviewUpdate, request: Request) -> CaseRead:
    actor = require_permission(request, Permission.CASE_REVIEW)
    _require_clinical_actor(actor)
    case = _get_case(request, case_id, actor)
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
