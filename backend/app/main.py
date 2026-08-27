from fastapi import FastAPI

app = FastAPI(title="KnowledgePilot")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
