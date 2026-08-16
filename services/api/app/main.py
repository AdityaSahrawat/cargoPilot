from fastapi import FastAPI

app = FastAPI(title="CargoPilot API")


@app.get("/")
def root():
    return {"status": "ok", "service": "cargoPilot-api"}
