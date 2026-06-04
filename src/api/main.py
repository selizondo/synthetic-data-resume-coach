"""FastAPI application for Synthetic Data Resume Coach."""

import os
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    try:
        logfire.configure(export_kwargs={"timeout": 5})
    except Exception:
        logfire.configure(send_to_logfire=False)
    logfire.info("Starting Synthetic Data Resume Coach API")
    yield
    logfire.info("Shutting down Synthetic Data Resume Coach API")


app = FastAPI(
    title="Synthetic Data Resume Coach",
    description="""
    Synthetic Data Resume Coach API for analyzing resumes against job descriptions.

    Features:
    - Resume-job fit analysis
    - Skills overlap calculation (Jaccard similarity)
    - Failure mode detection (6 metrics)
    - LLM-based quality assessment
    - Structured recommendations
    """,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Synthetic Data Resume Coach API",
        "version": "0.1.0",
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns process status plus LLM configuration check. Does NOT make a live
    LLM API call (too slow for a health probe) — instead validates that the
    required env vars are set and non-empty. A degraded response means the
    rule-based /review-resume path still works; only LLM judge calls will fail.
    """
    api_key = os.getenv("LLM_API_KEY", "")
    llm_configured = bool(api_key and api_key not in ("", "sk-no-key-required", "your-key-here"))

    return {
        "status": "healthy" if llm_configured else "degraded",
        "checks": {
            "llm_configured": llm_configured,
            "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            "llm_model": os.getenv("LLM_MODEL", "(not set)"),
            "rule_based_labeler": "available",  # always up — no external dependency
        },
    }
