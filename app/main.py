from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine

load_dotenv()
from .routers import export, health, ocr, receipts

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Receipt OCR System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Receipt OCR Backend is running",
        "docs": "/docs",
        "health": "/health",
        "scan": "/receipts/scan",
    }


app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(receipts.router)
app.include_router(export.router)
