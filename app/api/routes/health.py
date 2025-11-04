"""
Health check endpoints for monitoring and diagnostics.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session, db
from app.services.cache_service import get_cache
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def health_check():
    """Basic health check endpoint"""
    return {"status": "healthy", "message": "PDF Knowledge Miner API is running"}


@router.get("/detailed")
async def detailed_health_check(
    session: AsyncSession = Depends(get_db_session)
):
    """Detailed health check with database and cache status"""
    health_status = {
        "status": "healthy",
        "services": {},
        "timestamp": None
    }
    
    # Check database
    try:
        db_healthy = await db.health_check()
        health_status["services"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy",
            "details": "PostgreSQL connection successful" if db_healthy else "Connection failed"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["services"]["database"] = {
            "status": "unhealthy",
            "details": str(e)
        }
        health_status["status"] = "unhealthy"
    
    # Check cache
    try:
        cache_service = await get_cache()
        cache_healthy = await cache_service.health_check()
        health_status["services"]["cache"] = {
            "status": "healthy" if cache_healthy else "unhealthy",
            "details": "Redis connection successful" if cache_healthy else "Connection failed"
        }
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        health_status["services"]["cache"] = {
            "status": "unhealthy",
            "details": str(e)
        }
        health_status["status"] = "unhealthy"
    
    from datetime import datetime
    health_status["timestamp"] = datetime.utcnow().isoformat()
    
    return health_status


@router.get("/stats")
async def system_stats(
    session: AsyncSession = Depends(get_db_session)
):
    """Get system statistics"""
    try:
        # Database stats
        db_stats = await db.get_stats()
        
        # Cache stats
        cache_service = await get_cache()
        cache_stats = await cache_service.get_cache_info()
        
        return {
            "database": db_stats,
            "cache": cache_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        return {"error": str(e)}