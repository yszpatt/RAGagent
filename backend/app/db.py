from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pgvector.psycopg2 import register_vector

from app.core.config import settings

DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
# pgvector 的 psycopg2 适配器需在每个新连接上注册，否则 list 参数
# 会被绑定为 numeric[]，导致 `vector <=> numeric[]` 无匹配运算符。
# 在 db.py 统一注册，避免依赖 vector_store 的导入顺序。
# 注：connect 事件回调收到 (dbapi_conn, conn_record) 两个参数，需用 lambda 包装。
event.listen(engine, "connect", lambda dbapi_conn, _rec: register_vector(dbapi_conn))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
