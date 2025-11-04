"""
Admin endpoints for system management and monitoring.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging
from app.core.database import get_db_session
from app.services.cache_service import get_cache

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/process-all")
async def process_all_documents(
    background_tasks: BackgroundTasks,
    force_reprocess: bool = False,
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Process all documents in the PDF directory"""
    try:
        pdf_processor = request.app.state.pdf_processor
        
        background_tasks.add_task(
            process_all_task,
            pdf_processor,
            force_reprocess
        )
        
        return {"message": "Processing started for all documents"}
        
    except Exception as e:
        logger.error(f"Process all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_all_task(pdf_processor, force_reprocess: bool):
    """Background task to process all documents"""
    try:
        from app.core.database import db
        async with db.session() as session:
            result = await pdf_processor.process_pdf_directory(
                session=session,
                force_reprocess=force_reprocess
            )
            logger.info(f"Processing completed: {result}")
    except Exception as e:
        logger.error(f"Background processing failed: {e}")


@router.post("/reprocess-failed")
async def reprocess_failed_documents(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Reprocess documents that failed processing"""
    try:
        pdf_processor = request.app.state.pdf_processor
        
        background_tasks.add_task(
            reprocess_failed_task,
            pdf_processor
        )
        
        return {"message": "Reprocessing started for failed documents"}
        
    except Exception as e:
        logger.error(f"Reprocess failed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def reprocess_failed_task(pdf_processor):
    """Background task to reprocess failed documents"""
    try:
        from app.core.database import db
        async with db.session() as session:
            result = await pdf_processor.reprocess_failed_documents(session)
            logger.info(f"Reprocessing completed: {result}")
    except Exception as e:
        logger.error(f"Background reprocessing failed: {e}")


@router.post("/cache/clear")
async def clear_cache(
    cache_type: Optional[str] = None
):
    """Clear cache by type or all cache"""
    try:
        cache_service = await get_cache()
        
        cleared = await cache_service.clear_cache(cache_type)
        
        return {
            "message": f"Cache cleared successfully",
            "cache_type": cache_type or "all",
            "keys_cleared": cleared
        }
        
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/info")
async def get_cache_info():
    """Get cache information and statistics"""
    try:
        cache_service = await get_cache()
        
        info = await cache_service.get_cache_info()
        
        return info
        
    except Exception as e:
        logger.error(f"Cache info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/info")
async def get_system_info(
    session: AsyncSession = Depends(get_db_session)
):
    """Get system information and statistics"""
    try:
        from app.core.database import db
        from sqlalchemy import select, func
        from app.models.database import Document, DocumentChunk, SearchQuery
        
        # Database stats
        db_stats = await db.get_stats()
        
        # Document counts
        doc_count_result = await session.execute(select(func.count(Document.id)))
        doc_count = doc_count_result.scalar()
        
        chunk_count_result = await session.execute(select(func.count(DocumentChunk.id)))
        chunk_count = chunk_count_result.scalar()
        
        search_count_result = await session.execute(select(func.count(SearchQuery.id)))
        search_count = search_count_result.scalar()
        
        # Processing status counts
        status_counts_result = await session.execute(
            select(Document.processing_status, func.count(Document.id))
            .group_by(Document.processing_status)
        )
        status_counts = dict(status_counts_result.all())
        
        return {
            "database": db_stats,
            "documents": {
                "total": doc_count,
                "chunks": chunk_count,
                "searches": search_count,
                "status_counts": status_counts
            }
        }
        
    except Exception as e:
        logger.error(f"System info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))