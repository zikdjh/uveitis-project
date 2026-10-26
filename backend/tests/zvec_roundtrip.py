from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app
from app.db.audit import MemoryAuthAuditStore
from app.db.users import MemoryUserStore
from app.services.redis_store import MemorySessionStore
from app.services.knowledge import KnowledgeStore


def main() -> None:
    root = Path(__file__).parent.parent / ".zvec-test-data" / uuid4().hex
    app = create_app(
        upload_dir=root / "uploads",
        vector_dir=root / "vectors",
        use_environment_database=False,
        user_store=MemoryUserStore(),
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
    )
    settings = app.state.settings.model_copy(
        update={"vector_dimension": 4, "vector_provider": "memory"}
    )
    app.state.knowledge_store = KnowledgeStore(settings, root / "vectors")
    client = TestClient(app)
    vector = [1.0, 0.0, 0.0, 0.0]
    created = client.post(
        "/api/v1/knowledge/documents",
        json={
            "title": "Uveitis guideline",
            "content": "Posterior uveitis requires structured review.",
            "category": "guideline",
            "vector": vector,
        },
    )
    created.raise_for_status()
    matches = client.post(
        "/api/v1/knowledge/search",
        json={"vector": vector, "top_k": 5, "category": "guideline"},
    )
    matches.raise_for_status()
    assert matches.json()[0]["document"]["id"] == created.json()["id"]
    assert matches.json()[0]["score"] == 1.0
    status = client.get("/api/v1/knowledge/status")
    status.raise_for_status()
    assert status.json()["documents"] == 1
    print("zvec API round-trip passed")


if __name__ == "__main__":
    main()
