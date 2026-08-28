from fastapi import FastAPI
from app.api.v1 import admin, chat, conversations, documents

app = FastAPI(title="KnowledgePilot")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
