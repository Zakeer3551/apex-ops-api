from fastapi import FastAPI

app = FastAPI(title="Apex Operations API")


@app.get("/health")
def health():
    return {"status": "ok"}