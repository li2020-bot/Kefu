"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import chat, feedback, sessions
from src.core.config import settings
from src.core.db import init_db
from src.skills.registry import SkillRegistry



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Kefu customer service system starting...")
    # Initialize database tables (pgvector extension + knowledge_chunks)
    await init_db()
    logger.info("Database initialized")
    # Initialize skills registry
    SkillRegistry.load()
    logger.info("Skills registry initialized")
    yield
    logger.info("Kefu customer service system shutting down...")


app = FastAPI(
    title="Kefu - Enterprise Customer Service System",
    description="Intelligent customer service powered by LangGraph, RAG, and MCP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(chat.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "kefu"}


@app.get("/api/v1/skills")
async def list_skills():
    """List all available customer service skills."""
    return {"skills": SkillRegistry.list_all()}


# Serve the static chat page at /
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open(os.path.join(_STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# Mount static files directory
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=settings.api_port, reload=settings.debug)
