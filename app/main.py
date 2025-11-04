"""
FastAPI application with async endpoints for document management and search.
Provides REST API for the PDF Knowledge Miner service.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
from typing import List, Optional, Dict, Any
from app.core.config import get_settings
from app.core.database import init_db, close_db, get_db_session
from app.services.cache_service import init_cache, close_cache, get_cache
from app.services.pdf_processor import PDFProcessor
from app.services.search_service import SearchService
from app.api.routes import documents, search, health, admin
from app.core.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown handlers"""
    # Startup
    logger.info("Starting PDF Knowledge Miner API...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized successfully")
        
        # Initialize cache
        await init_cache()
        logger.info("Cache initialized successfully")
        
        # Initialize services
        cache_service = await get_cache()
        search_service = SearchService(cache_service)
        
        # Store services in app state  
        app.state.search_service = search_service
        app.state.pdf_processor = PDFProcessor()
        app.state.cache_service = cache_service
        
        logger.info("PDF Knowledge Miner API started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    finally:
        # Shutdown
        logger.info("Shutting down PDF Knowledge Miner API...")
        try:
            await close_db()
            await close_cache()
            logger.info("Database and cache connections closed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        logger.info("Application shutdown complete")
        
        try:
            await close_cache()
            await close_db()
            logger.info("Application shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.api.title,
        description=settings.api.description,
        version=settings.api.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.cors_origins,
        allow_credentials=True,
        allow_methods=settings.security.cors_methods,
        allow_headers=settings.security.cors_headers,
    )
    
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Include routers
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)}
        )
    
    return app


# Create app instance
app = create_app()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    settings = get_settings()
    return {
        "name": settings.api.title,
        "version": settings.api.version,
        "description": settings.api.description,
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": "/api/v1"
    }


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        workers=settings.api.workers,
        log_level=settings.logging.level.lower(),
    )