"""
Document management endpoints for uploading, processing, and managing PDFs.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
import aiofiles
import os
from pathlib import Path
import logging
from app.core.database import get_db_session
from app.core.config import get_settings
from app.models.database import Document, DocumentChunk
from app.services.pdf_processor import PDFProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Upload and process a PDF document"""
    settings = get_settings()
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Validate file size
    file_size = 0
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Seek back to beginning
    
    max_size = settings.processing.max_file_size_mb * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=400, 
            detail=f"File size exceeds limit of {settings.processing.max_file_size_mb}MB"
        )
    
    try:
        # Save file to PDF directory
        pdf_dir = Path(settings.processing.pdf_dir)
        pdf_dir.mkdir(exist_ok=True)
        
        file_path = pdf_dir / file.filename
        
        # Check if file already exists
        existing_doc = await session.execute(
            select(Document).where(Document.filename == file.filename)
        )
        if existing_doc.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Document with filename '{file.filename}' already exists"
            )
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Process document in background
        pdf_processor = request.app.state.pdf_processor
        background_tasks.add_task(
            process_document_task,
            str(file_path),
            pdf_processor
        )
        
        return {
            "message": "Document uploaded successfully",
            "filename": file.filename,
            "file_size": file_size,
            "status": "processing"
        }
        
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_document_task(file_path: str, pdf_processor: PDFProcessor):
    """Background task to process uploaded document"""
    try:
        from app.core.database import db
        async with db.session() as session:
            await pdf_processor.process_single_pdf(Path(file_path), session)
    except Exception as e:
        logger.error(f"Background processing failed for {file_path}: {e}")


@router.get("/")
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session)
):
    """List documents with optional filtering"""
    try:
        query = select(Document)
        
        # Filter by status
        if status:
            query = query.where(Document.processing_status == status)
        
        # Search by filename or title
        if search:
            search_term = f"%{search}%"
            query = query.where(
                Document.filename.ilike(search_term) |
                Document.title.ilike(search_term)
            )
        
        # Pagination
        query = query.offset(skip).limit(limit).order_by(Document.created_at.desc())
        
        result = await session.execute(query)
        documents = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(Document.id))
        if status:
            count_query = count_query.where(Document.processing_status == status)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                Document.filename.ilike(search_term) |
                Document.title.ilike(search_term)
            )
        
        total_result = await session.execute(count_query)
        total = total_result.scalar()
        
        return {
            "documents": [
                {
                    "id": str(doc.id),
                    "filename": doc.filename,
                    "title": doc.title,
                    "author": doc.author,
                    "pages_count": doc.pages_count,
                    "file_size": doc.file_size,
                    "processing_status": doc.processing_status,
                    "created_at": doc.created_at.isoformat(),
                    "processed_at": doc.processed_at.isoformat() if doc.processed_at else None
                }
                for doc in documents
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Get document details by ID"""
    try:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get chunk count
        chunk_count_result = await session.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
        )
        chunk_count = chunk_count_result.scalar()
        
        return {
            "id": str(document.id),
            "filename": document.filename,
            "title": document.title,
            "author": document.author,
            "subject": document.subject,
            "pages_count": document.pages_count,
            "file_size": document.file_size,
            "file_hash": document.file_hash,
            "processing_status": document.processing_status,
            "error_message": document.error_message,
            "chunks_count": chunk_count,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
            "processed_at": document.processed_at.isoformat() if document.processed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Delete document and its chunks"""
    try:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete file if it exists
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        # Delete document (chunks will be cascade deleted)
        await session.delete(document)
        await session.commit()
        
        return {"message": "Document deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
):
    """Reprocess a document"""
    try:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if not os.path.exists(document.file_path):
            raise HTTPException(status_code=400, detail="Document file not found")
        
        # Reprocess in background
        pdf_processor = request.app.state.pdf_processor
        background_tasks.add_task(
            reprocess_document_task,
            document_id,
            document.file_path,
            pdf_processor
        )
        
        return {"message": "Document reprocessing started"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def reprocess_document_task(document_id: str, file_path: str, pdf_processor: PDFProcessor):
    """Background task to reprocess document"""
    try:
        from app.core.database import db
        async with db.session() as session:
            await pdf_processor.process_single_pdf(Path(file_path), session, force_reprocess=True)
    except Exception as e:
        logger.error(f"Background reprocessing failed for {document_id}: {e}")


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session)
):
    """Get document chunks with pagination"""
    try:
        # Verify document exists
        doc_result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        if not doc_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get chunks
        chunks_query = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        ).order_by(
            DocumentChunk.page_number, DocumentChunk.chunk_index
        ).offset(skip).limit(limit)
        
        result = await session.execute(chunks_query)
        chunks = result.scalars().all()
        
        # Get total count
        count_result = await session.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
        )
        total = count_result.scalar()
        
        return {
            "chunks": [
                {
                    "id": str(chunk.id),
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "text_content": chunk.text_content,
                    "text_length": chunk.text_length,
                    "embedding_model": chunk.embedding_model,
                    "created_at": chunk.created_at.isoformat()
                }
                for chunk in chunks
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))