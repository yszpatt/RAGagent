"""pytest 配置：测试库与开发库物理隔离。

为什么必须隔离
--------------
tests/test_pipeline.py 与 tests/test_vector_store.py 的 clean_tables fixture
会无条件整表 DELETE（DELETE FROM documents / workspaces，无 WHERE），
而旧配置的 TEST_DATABASE_URL 默认指向开发库 knowledgepilot。
后果：**跑一次 pytest 就会抹掉开发者整个知识库** —— 这是实测发生过的事故
（一次全量测试后，已上传的 7 篇文档与全部 chunk 被清空），不是假想风险。

本文件做四件事：
  1. 默认把测试指向独立库 knowledgepilot_test；
  2. 该库不存在时自动创建并灌入 sql/schema.sql；
  3. 显式拒绝指向开发库（除非设 KP_ALLOW_DESTRUCTIVE_TESTS=1）；
  4. 把 DATABASE_URL 指到测试库。

第 4 点为什么必须在 import 期完成：app/db.py 在模块导入时就执行
`engine = create_engine(settings.database_url)`，而 conftest.py 早于任何测试模块
被导入。若改成 fixture 里再改环境变量，app.db.engine 早已绑定到开发库，
于是出现「测试用 engine 写、API 用 SessionLocal 读，两个库互相看不见」的怪象
（实测表现为大量 404）。
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = "postgresql://kp:kp@localhost:5432/knowledgepilot_test"

_SCHEMA_SQL = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"

# 允许整表清空的库名特征：必须一眼能看出是测试库
_SAFE_NAME_MARKERS = ("_test", "test_", "_pytest")


def _looks_like_test_database(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(m in lowered for m in _SAFE_NAME_MARKERS)


def _apply_schema(url) -> None:
    """灌入 schema.sql。逐条执行，避免多语句字符串在不同驱动上的行为差异。"""
    raw = _SCHEMA_SQL.read_text(encoding="utf-8")
    statements, buf = [], []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buf = []
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            for stmt in statements:
                conn.execute(text(stmt))
    finally:
        engine.dispose()


def _bootstrap() -> str:
    url_str = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    url = make_url(url_str)

    if not _looks_like_test_database(url.database):
        if os.environ.get("KP_ALLOW_DESTRUCTIVE_TESTS") != "1":
            pytest.exit(
                f"\n拒绝在数据库 {url.database!r} 上运行测试：\n"
                f"  clean_tables 之类的 fixture 会整表清空，会毁掉真实数据。\n"
                f"  请改用独立测试库（默认 {DEFAULT_TEST_DATABASE_URL}），\n"
                f"  或显式设 KP_ALLOW_DESTRUCTIVE_TESTS=1 确认你愿意清空该库。\n",
                returncode=2,
            )

    # 库不存在则创建（需先连到 postgres 库执行 CREATE DATABASE）
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :d"),
                {"d": url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()

    _apply_schema(url)
    return url_str


TEST_DATABASE_URL = _bootstrap()

# 关键：必须在任何 app.* 模块被导入之前设置，否则 app.db.engine 会绑到开发库。
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture
def engine():
    return create_engine(TEST_DATABASE_URL)
