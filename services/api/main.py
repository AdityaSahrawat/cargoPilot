from fastapi import FastAPI
import uvicorn

from app.api import health
from app.api.v1 import api_v1_router

app = FastAPI(title="CargoPilot API", version="1.0.0")


@app.get("/")
def root():
    return {"status": "ok", "service": "cargoPilot-api"}


app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(api_v1_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
