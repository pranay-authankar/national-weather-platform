from fastapi import FastAPI

app = FastAPI(
    title="National Weather Big Data Analytics Platform API",
    version="0.1.0",
)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
