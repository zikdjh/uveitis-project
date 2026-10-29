from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DictionaryValueType = Literal[
    "string",
    "int",
    "float",
    "bool",
    "json",
    "secret",
]


class DataDictionaryEntryRead(BaseModel):
    id: str
    namespace: str
    key: str
    value_type: DictionaryValueType
    value: Any | None = None
    configured: bool = False
    is_secret: bool = False
    description: str = ""
    revision: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str = ""


class DataDictionaryEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None = None
    value_type: DictionaryValueType | None = None
    description: str | None = Field(default=None, max_length=500)
    expected_revision: int | None = Field(default=None, ge=0)
