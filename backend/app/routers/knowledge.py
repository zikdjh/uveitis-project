from fastapi import APIRouter, HTTPException, Request

from app.core.security import require_role
from app.schemas.case import (
    KnowledgeDocument,
    KnowledgeDocumentCreate,
    KnowledgeIndexStatus,
    KnowledgeMatch,
    KnowledgeSearchRequest,
)


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.post("/documents", response_model=KnowledgeDocument, status_code=201)
def add_document(
    payload: KnowledgeDocumentCreate, request: Request
) -> KnowledgeDocument:
    require_role(request, "admin")
    try:
        return request.app.state.knowledge_store.add(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"zvec 写入失败: {exc}") from exc


@router.post("/search", response_model=list[KnowledgeMatch])
def search_knowledge(
    payload: KnowledgeSearchRequest, request: Request
) -> list[KnowledgeMatch]:
    require_role(request, "doctor", "admin")
    try:
        return request.app.state.knowledge_store.search(
            payload.query,
            payload.vector,
            payload.top_k,
            payload.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"zvec 检索失败: {exc}") from exc


@router.get("/status", response_model=KnowledgeIndexStatus)
def knowledge_status(request: Request) -> KnowledgeIndexStatus:
    return request.app.state.knowledge_store.status()
