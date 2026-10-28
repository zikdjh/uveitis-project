from __future__ import annotations


TABLE_PREFIX = "t_"
COLUMN_PREFIX = "f_"


def table_name(business_name: str) -> str:
    return f"{TABLE_PREFIX}{business_name}"


def column_name(business_name: str) -> str:
    return f"{COLUMN_PREFIX}{business_name}"


PRIMARY_KEY_COLUMN = column_name("id")

BUSINESS_KEY_COLUMNS = {
    table_name("user"): column_name("user_key"),
    table_name("case"): column_name("case_key"),
    table_name("analysis_job"): column_name("job_key"),
    table_name("data_dictionary"): column_name("dictionary_key"),
    table_name("auth_audit_event"): column_name("event_key"),
    table_name("integration_setting"): column_name("setting_key"),
}


LEGACY_TABLE_RENAMES = {
    "users": table_name("user"),
    "cases": table_name("case"),
    "analysis_jobs": table_name("analysis_job"),
    "auth_audit_events": table_name("auth_audit_event"),
    "data_dictionary": table_name("data_dictionary"),
    "integration_settings": table_name("integration_setting"),
}

LEGACY_COLUMN_RENAMES = {
    table_name("user"): {
        "id": column_name("id"),
        "username": column_name("username"),
        "display_name": column_name("display_name"),
        "role": column_name("role"),
        "password_hash": column_name("password_hash"),
        "is_active": column_name("is_active"),
        "created_at": column_name("created_at"),
    },
    table_name("case"): {
        "id": column_name("id"),
        "owner_id": column_name("owner_id"),
        "status": column_name("status"),
        "created_at": column_name("created_at"),
        "updated_at": column_name("updated_at"),
        "payload_json": column_name("payload_json"),
    },
    table_name("analysis_job"): {
        "id": column_name("id"),
        "job_key": column_name("job_key"),
        "status": column_name("status"),
        "created_at": column_name("created_at"),
        "updated_at": column_name("updated_at"),
    },
    table_name("auth_audit_event"): {
        "id": column_name("id"),
        "event": column_name("event"),
        "outcome": column_name("outcome"),
        "username": column_name("username"),
        "user_id": column_name("user_id"),
        "actor_id": column_name("actor_id"),
        "ip_address": column_name("ip_address"),
        "user_agent": column_name("user_agent"),
        "detail": column_name("detail"),
        "created_at": column_name("created_at"),
    },
    table_name("data_dictionary"): {
        "id": column_name("id"),
        "namespace": column_name("namespace"),
        "key": column_name("key"),
        "value_type": column_name("value_type"),
        "value_text": column_name("value_text"),
        "is_secret": column_name("is_secret"),
        "description": column_name("description"),
        "revision": column_name("revision"),
        "created_at": column_name("created_at"),
        "updated_at": column_name("updated_at"),
        "updated_by": column_name("updated_by"),
    },
    table_name("integration_setting"): {
        "id": column_name("id"),
        "revision": column_name("revision"),
        "payload_json": column_name("payload_json"),
        "updated_at": column_name("updated_at"),
        "updated_by": column_name("updated_by"),
    },
}
