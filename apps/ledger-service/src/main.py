from fastapi import FastAPI

app = FastAPI(title="ledger-service API", version="0.1.0")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ledger-service"}
