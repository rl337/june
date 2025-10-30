import os
import json
from typing import Any, Dict
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="Mock Sink", version="0.1.0")

ARTIFACTS_DIR = "/app/model_artifacts"
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
REQUEST_LOG = os.path.join(ARTIFACTS_DIR, "requests.jsonl")


class RecordPayload(BaseModel):
    path: str
    headers: Dict[str, Any] | None = None
    body: Dict[str, Any] | None = None


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"healthy": True}


@app.post("/record")
async def record(request: Request) -> Dict[str, Any]:
    body: Dict[str, Any] | None = None
    try:
        body = await request.json()
    except Exception:
        body = None

    entry = {
        "path": str(request.url.path),
        "query": str(request.url.query),
        "method": request.method,
        "headers": {k: v for k, v in request.headers.items()},
        "body": body,
    }
    with open(REQUEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return {"status": "ok"}




