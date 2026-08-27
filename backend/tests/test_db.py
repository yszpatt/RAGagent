import os
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def engine():
    url = os.environ.get("TEST_DATABASE_URL", "postgresql://kp:kp@localhost:5432/knowledgepilot")
    return create_engine(url)


def test_schema_tables_exist(engine):
    with engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )).fetchall()
        names = {t[0] for t in tables}
        required = {"documents", "chunks", "document_permissions",
                    "conversations", "messages", "audit_logs", "ingestion_jobs"}
        assert required.issubset(names)


def test_pgvector_extension_installed(engine):
    with engine.connect() as conn:
        ext = conn.execute(text("SELECT extname FROM pg_extension")).fetchall()
        assert ("vector",) in ext
