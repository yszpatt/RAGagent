"""demo 单用户上下文：默认 workspace + 默认 user。

会话持久化与审计埋点都需要 user_id / workspace_id（NOT NULL 外键）。
demo 未接鉴权，统一落到「本地默认用户」，接 SSO 后由认证上下文替换。
"""
import uuid

from sqlalchemy import text

from app.db import SessionLocal

DEFAULT_WORKSPACE_NAME = "默认工作区"
DEFAULT_USER_EXTERNAL_ID = "demo-local"


def default_workspace_id() -> uuid.UUID:
    """返回第一个 workspace；不存在则创建默认工作区。"""
    with SessionLocal() as s:
        row = s.execute(text(
            "SELECT id FROM workspaces ORDER BY created_at LIMIT 1"
        )).first()
        if row:
            return row[0]
        ws_id = uuid.uuid4()
        s.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, :name)"
        ), {"id": ws_id, "name": DEFAULT_WORKSPACE_NAME})
        s.commit()
        return ws_id


def default_user_id() -> uuid.UUID:
    """返回默认用户；不存在则创建（admin 角色）。"""
    with SessionLocal() as s:
        row = s.execute(text(
            "SELECT id FROM users WHERE external_id = :ext"
        ), {"ext": DEFAULT_USER_EXTERNAL_ID}).first()
        if row:
            return row[0]
        user_id = uuid.uuid4()
        s.execute(text(
            "INSERT INTO users (id, external_id, role, workspace_id) "
            "VALUES (:id, :ext, 'admin', :ws)"
        ), {"id": user_id, "ext": DEFAULT_USER_EXTERNAL_ID,
            "ws": default_workspace_id()})
        s.commit()
        return user_id
