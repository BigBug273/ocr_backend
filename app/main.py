from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

# API routers first (they take priority over the catch-all)
app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(receipts.router)
app.include_router(export.router)

# ─── Serve Frontend (must be LAST) ───
static_dir = os.path.join(os.path.dirname(__file__), "../static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend files. Fallback to index.html."""
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))