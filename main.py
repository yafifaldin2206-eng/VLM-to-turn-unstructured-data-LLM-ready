"""
VISIONARY — Multimodal Structured Extraction API
SOTA vision models → structured data for LLMs, agents, and automation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uuid

from app.core.config import settings
from app.core.logging import get_logger
from app.api.v1.router import api_router
from app.core.middleware import RateLimitMiddleware
from app.services.job_store import job_store

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 VISIONARY API starting up", version=settings.VERSION)
    await job_store.initialize()
    yield
    logger.info("🛑 VISIONARY API shutting down")
    await job_store.close()


app = FastAPI(
    title="VISIONARY API",
    description="""
## VISIONARY — Multimodal Structured Extraction API

Transform **any visual data** into production-ready structured formats using SOTA vision models.

### Capabilities
- 🖼️ **Images** — JPEG, PNG, WebP, GIF, TIFF
- 📄 **PDFs** — Single and multi-page document extraction
- 🌐 **URLs** — Web screenshots and remote image ingestion
- 🔢 **Base64** — Direct binary ingestion

### Extraction Modes
- **Schema-driven** — Provide a JSON Schema, get back validated structured data
- **Auto-detect** — Let the model infer the optimal structure
- **Template** — Use pre-built templates (invoice, receipt, form, table, etc.)

### Features
- Multi-provider routing (Claude, GPT-4V, Gemini) with automatic fallback
- Async batch processing with webhook callbacks
- Confidence scoring per field
- Diff-aware re-extraction for incremental updates
    """,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware runs in reverse registration order (last added = first to run).
# Auth is handled via FastAPI dependency on the v1 router.
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", exc_info=exc, path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# Mount v1 router
app.include_router(api_router, prefix="/v1")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "VISIONARY API",
        "version": settings.VERSION,
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    store_healthy = await job_store.ping()
    return {
        "status": "healthy" if store_healthy else "degraded",
        "version": settings.VERSION,
        "components": {
            "job_store": "healthy" if store_healthy else "unhealthy",
        },
    }
