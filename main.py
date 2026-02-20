from fastapi import FastAPI
from bidvault.api.ingest import router as ingest_router
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="BidVault Ingestion Pipeline",
    description="API for ingesting and searching bid documents",
    version="1.0.0"
)

# Include the ingestion router
app.include_router(ingest_router, prefix="/api/ingest", tags=["ingestion"])

@app.get("/")
async def root():
    return {"message": "BidVault Ingestion Pipeline is running"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
