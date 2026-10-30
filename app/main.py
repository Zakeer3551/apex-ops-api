import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Response
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


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.get("/health")
def health():
    return {"status": "okay"}


@app.get("/ready")
def ready(response: Response):
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except psycopg.Error:
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
