from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.audit import AuthAuditStore
from app.db.models import Base
from app.db.users import UserStore


def make_session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth-stores.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def test_sqlalchemy_user_store_supports_role_and_status(tmp_path: Path) -> None:
    store = UserStore(make_session_factory(tmp_path))
    user = store.create("store.doctor", "hash", "存储医生", "doctor")
    assert user.role == "doctor"
    assert user.is_active is True

    updated = store.update(user.id, role="admin", is_active=False)
    assert updated is not None
    assert updated.role == "admin"
    assert updated.is_active is False
    assert store.count_active_admins() == 0


def test_sqlalchemy_audit_store_records_event(tmp_path: Path) -> None:
    store = AuthAuditStore(make_session_factory(tmp_path))
    event = store.record(
        event="login",
        outcome="success",
        username="Store.Doctor",
        user_id="user-1",
        actor_id=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    assert event.username == "store.doctor"
    assert store.list()[0].event == "login"
