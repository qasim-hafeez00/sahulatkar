from fastapi import FastAPI

app = FastAPI(title="payment-orchestrator API", version="0.1.0")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "payment-orchestrator"}
