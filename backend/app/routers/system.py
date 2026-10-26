from fastapi import APIRouter, Request

from app.core.security import require_permission
from app.schemas.auth import Permission
from app.schemas.case import ModelService, SystemOverview


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/overview", response_model=SystemOverview)
def overview(request: Request) -> SystemOverview:
    require_permission(request, Permission.SYSTEM_READ)
    return SystemOverview(
        stats=request.app.state.case_store.stats(),
        model_mode=request.app.state.settings.model_mode,
        models=[
            *request.app.state.analysis_service.model_services(),
            ModelService(
                role="向量数据库",
                name="zvec",
                status=(
                    "configured"
                    if request.app.state.knowledge_store.repository.exists()
                    else "offline"
                ),
                endpoint=str(request.app.state.knowledge_store.repository.path),
            ),
        ],
        disclaimer="科研原型输出仅供辅助参考，不构成临床诊断，所有结论必须由医生复核。",
    )


@router.get("/infrastructure")
def infrastructure(request: Request) -> dict[str, bool]:
    require_permission(request, Permission.SYSTEM_MANAGE)
    case_store = request.app.state.case_store
    return {
        "postgres": (
            case_store.ping() if hasattr(case_store, "ping") else False
        ),
        "redis": request.app.state.redis_store.ping(),
    }
