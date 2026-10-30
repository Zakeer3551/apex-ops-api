import os
import json
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field


def get_conn():
    return psycopg.connect(os.environ.get("DATABASE_URL", ""), connect_timeout=2)


@asynccontextmanager
async def lifespan(app):
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS items ("
            "id SERIAL PRIMARY KEY, name TEXT NOT NULL)"
        )
    yield


app = FastAPI(title="Apex Operations API", lifespan=lifespan)


def log(level, event, **fields):
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **fields,
    }
    print(json.dumps(record), flush=True)


@app.middleware("http")
async def log_requests(request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log(
            "error",
            "unhandled_error",
            method=request.method,
            path=request.url.path,
            error=type(exc).__name__,
            request_id=request_id,
        )
        raise
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["x-request-id"] = request_id
    log(
        "info",
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        request_id=request_id,
    )
    return response


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": os.environ.get("APP_VERSION", "dev")}


@app.get("/ready")
def ready(response: Response):
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except psycopg.Error as exc:
        log("warning", "readiness_failed", error=type(exc).__name__)
        response.status_code = 503
        return {"status": "not ready", "reason": "database unreachable"}


@app.post("/items", status_code=201)
def create_item(item: ItemIn):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO items (name) VALUES (%s) RETURNING id, name",
            (item.name,),
        ).fetchone()
    return {"id": row[0], "name": row[1]}


@app.get("/items")
def list_items():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name FROM items ORDER BY id").fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


@app.get("/items/{item_id}")
def get_item(item_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name FROM items WHERE id = %s", (item_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"id": row[0], "name": row[1]}
