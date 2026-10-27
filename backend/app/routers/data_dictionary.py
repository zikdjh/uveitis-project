from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.security import (
    request_ip,
    request_user_agent,
    require_permission,
)
from app.schemas.auth import Permission
from app.schemas.data_dictionary import (
    DataDictionaryEntryRead,
    DataDictionaryEntryUpdate,
)


router = APIRouter(
    prefix="/api/v1/admin/data-dictionary",
    tags=["data-dictionary"],
)

PROTECTED_WRITE_NAMESPACES = frozenset({"auth", "integration"})


def _ensure_writable(namespace: str) -> None:
    if namespace in PROTECTED_WRITE_NAMESPACES:
        raise HTTPException(
            status_code=409,
            detail="该命名空间由系统维护，请通过对应管理功能操作",
        )


def _audit(
    request: Request,
    *,
    event: str,
    actor,
    namespace: str,
    key: str,
) -> None:
    request.app.state.audit_store.record(
        event=event,
        outcome="success",
        username=actor.username,
        user_id=actor.id,
        actor_id=actor.id,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
        detail=f"数据字典 {namespace}/{key}",
    )


@router.get("", response_model=list[DataDictionaryEntryRead])
def list_entries(
    request: Request,
    namespace: str | None = Query(default=None, max_length=100),
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DataDictionaryEntryRead]:
    require_permission(request, Permission.DATA_DICTIONARY_READ)
    return request.app.state.data_dictionary_store.list_entries(
        namespace=namespace,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{namespace}/{key}", response_model=DataDictionaryEntryRead)
def get_entry(namespace: str, key: str, request: Request) -> DataDictionaryEntryRead:
    require_permission(request, Permission.DATA_DICTIONARY_READ)
    entry = request.app.state.data_dictionary_store.get_entry(namespace, key)
    if entry is not None:
        return entry
    raise HTTPException(status_code=404, detail="数据字典项不存在")


@router.put("/{namespace}/{key}", response_model=DataDictionaryEntryRead)
def upsert_entry(
    namespace: str,
    key: str,
    payload: DataDictionaryEntryUpdate,
    request: Request,
) -> DataDictionaryEntryRead:
    actor = require_permission(request, Permission.DATA_DICTIONARY_MANAGE)
    _ensure_writable(namespace)
    try:
        entry = request.app.state.data_dictionary_store.set_value(
            namespace,
            key,
            payload.value,
            value_type=payload.value_type,
            description=payload.description,
            actor_id=actor.id,
            expected_revision=payload.expected_revision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        request,
        event="data_dictionary_update",
        actor=actor,
        namespace=namespace,
        key=key,
    )
    return entry


@router.delete("/{namespace}/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    namespace: str,
    key: str,
    request: Request,
    expected_revision: int | None = Query(default=None, ge=0),
) -> Response:
    actor = require_permission(request, Permission.DATA_DICTIONARY_MANAGE)
    _ensure_writable(namespace)
    try:
        deleted = request.app.state.data_dictionary_store.delete_value(
            namespace,
            key,
            actor_id=actor.id,
            expected_revision=expected_revision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="数据字典项不存在")
    _audit(
        request,
        event="data_dictionary_delete",
        actor=actor,
        namespace=namespace,
        key=key,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
