import os

import psycopg
from fastapi import FastAPI, Response

app = FastAPI(title="Apex Operations API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(response: Response):
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        with psycopg.connect(database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return {"status": "ready"}
    except psycopg.Error:
        response.status_code = 503
        return {"status": "not ready", "reason": "database unreachable"}
