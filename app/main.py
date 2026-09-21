from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.config import settings
from app.storage.database import init_db
from app.worker import start_worker, stop_worker
from app.web.api import router as api_router

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    start_worker()
    yield
    # Shutdown
    stop_worker()

app = FastAPI(
    title="AI & Data Science News Intelligence Engine",
    description="RAG over fresh tech, AI, and data science news with prioritized scoring and citations.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Mount static folder
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    favicon_ico = STATIC_DIR / "favicon.ico"
    if favicon_ico.exists():
        return FileResponse(favicon_ico, media_type="image/x-icon")
    favicon_svg = STATIC_DIR / "favicon.svg"
    if favicon_svg.exists():
        return FileResponse(favicon_svg, media_type="image/svg+xml")
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def chrome_devtools_probe():
    return Response(content="{}", media_type="application/json")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AI & Tech News Engine running. UI assets under preparation."}

