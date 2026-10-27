"""Hard privacy boundary for third-party API calls.

Images and case records never leave the deployment. Every payload bound for
an external endpoint (external summary, web search, tool-chain planner) is
sanitized and then verified here, so a future change cannot reintroduce case
fields or image data by accident.

Allowed content: model-derived labels, evidence snippets returned by the
local knowledge index, and search results. Forbidden content: raw case fields
such as complaint, history, age, sex, affected eye, case id, review records,
image metadata, image paths and inline binary data.
"""

from __future__ import annotations

from typing import Any


BLOCKED_CASE_KEYS = frozenset(
    {
        "case",
        "case_id",
        "case_key",
        "patient",
        "patient_age",
        "patient_sex",
        "complaint",
        "medical_history",
        "affected_eye",
        "consent_confirmed",
        "clinical_context",
        "review",
        "reviewer",
    }
)
"""Case fields that must never appear in a third-party payload."""

BLOCKED_IMAGE_KEYS = frozenset(
    {
        "images",
        "image",
        "image_id",
        "image_url",
        "local_path",
        "file_path",
        "filename",
        "content_type",
        "size_bytes",
        "base64",
        "data_uri",
        "binary",
    }
)
"""Image fields that must never appear in a third-party payload."""

BLOCKED_KEYS = BLOCKED_CASE_KEYS | BLOCKED_IMAGE_KEYS

BINARY_URI_PREFIXES = (
    "data:image/",
    "data:application/octet-stream",
    "data:application/dicom",
)

REDACTED = "[redacted-外部接口不接收病例或影像数据]"

MAX_SCAN_DEPTH = 12


def _clean(value: Any, depth: int) -> Any:
    if depth > MAX_SCAN_DEPTH:
        return REDACTED
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.startswith(BINARY_URI_PREFIXES):
            return REDACTED
        return value
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.strip().lower() in BLOCKED_KEYS:
                continue
            cleaned[str(key)] = _clean(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_clean(item, depth + 1) for item in value]
    return value


def sanitize_external_payload(value: Any) -> Any:
    """Return a copy without case fields, image fields or inline binaries."""

    return _clean(value, 0)


def find_external_violations(
    value: Any,
    path: str = "$",
    depth: int = 0,
) -> list[str]:
    """List every case or image violation in a payload."""

    if depth > MAX_SCAN_DEPTH:
        return [f"{path}: 嵌套层级过深"]
    violations: list[str] = []
    if isinstance(value, str):
        if value.strip().lower().startswith(BINARY_URI_PREFIXES):
            violations.append(f"{path}: 内联影像数据")
        return violations
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(key, str) and key.strip().lower() in BLOCKED_KEYS:
                violations.append(f"{child}: 禁止字段")
            violations.extend(find_external_violations(item, child, depth + 1))
        return violations
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            violations.extend(
                find_external_violations(item, f"{path}[{index}]", depth + 1)
            )
    return violations


def assert_external_payload(value: Any, *, service: str) -> Any:
    """Refuse a payload that carries case or image data.

    This is a hard check on the value it is given. Send paths sanitize first
    and then call this as a postcondition, so nothing can leave the process
    even if a future change reintroduces a case field upstream.
    """

    violations = find_external_violations(value)
    if violations:
        raise ValueError(
            f"{service} 载荷包含病例或影像数据：" + "；".join(violations[:5])
        )
    return value


def prepare_external_payload(value: Any, *, service: str) -> Any:
    """Sanitize a payload, then verify the result before it is sent."""

    return assert_external_payload(
        sanitize_external_payload(value),
        service=service,
    )


def assert_external_text(text: str, case: Any, *, service: str) -> str:
    """Refuse to send free text that quotes a case field verbatim."""

    for field in ("complaint", "medical_history"):
        raw = str(getattr(case, field, "") or "").strip()
        if raw and raw in text:
            raise ValueError(
                f"{service} 请求文本包含病例字段 {field}，已拒绝外发"
            )
    return prepare_external_payload(text, service=service)
