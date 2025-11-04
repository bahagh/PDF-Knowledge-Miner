"""
Search endpoints for semantic search and question answering.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import logging
from app.core.database import get_db_session
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/")
async def search_documents(
    query: str,
    top_k: Optional[int] = Query(5, ge=1, le=50),
    similarity_threshold: Optional[float] = Query(0.7, ge=0.0, le=1.0),
    document_ids: Optional[List[str]] = Query(None),
    include_qa: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """
    Perform semantic search across documents.
    
    Args:
        query: Search query text
        top_k: Number of results to return (1-50)
        similarity_threshold: Minimum similarity score (0.0-1.0)
        document_ids: Limit search to specific documents
        include_qa: Include question-answering results
    """
    try:
        if not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        search_service: SearchService = request.app.state.search_service
        
        # Get client information for tracking
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")
        
        if include_qa:
            results = await search_service.search_with_qa(
                session=session,
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                document_ids=document_ids,
                ip_address=client_ip,
                user_agent=user_agent
            )
        else:
            results = await search_service.semantic_search(
                session=session,
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                document_ids=document_ids,
                ip_address=client_ip,
                user_agent=user_agent
            )
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/similar-documents/{document_id}")
async def get_similar_documents(
    document_id: str,
    top_k: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Find documents similar to a given document"""
    try:
        search_service: SearchService = request.app.state.search_service
        
        results = await search_service.get_similar_documents(
            session=session,
            document_id=document_id,
            top_k=top_k
        )
        
        return {
            "document_id": document_id,
            "similar_documents": results,
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Similar documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_search_analytics(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Get search analytics and statistics"""
    try:
        search_service: SearchService = request.app.state.search_service
        
        analytics = await search_service.get_search_analytics(
            session=session,
            days=days
        )
        
        return analytics
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))