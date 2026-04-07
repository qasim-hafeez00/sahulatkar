from fastapi import FastAPI

app = FastAPI(title="product-service API", version="0.1.0")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "product-service"}
