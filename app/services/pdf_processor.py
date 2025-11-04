"""
Optimized PDF processing service with chunking and parallel processing.
Uses PyMuPDF for fast text extraction and intelligent text chunking.
"""
import asyncio
import hashlib
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.config import get_settings
from app.models.database import Document, DocumentChunk
from app.utils.text_processing import TextChunker

logger = logging.getLogger(__name__)


class PDFProcessor:
    """High-performance PDF processing with parallel execution"""
    
    def __init__(self):
        self.settings = get_settings()
        self.text_chunker = TextChunker(
            max_chunk_size=self.settings.ml.max_chunk_size,
            chunk_overlap=self.settings.ml.chunk_overlap
        )
        self.embedding_model = None
        self._model_lock = asyncio.Lock()
    
    async def get_embedding_model(self) -> SentenceTransformer:
        """Get or initialize the embedding model (thread-safe singleton)"""
        if self.embedding_model is None:
            async with self._model_lock:
                if self.embedding_model is None:
                    logger.info(f"Loading embedding model: {self.settings.ml.embedding_model}")
                    # Load model in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    self.embedding_model = await loop.run_in_executor(
                        None, 
                        SentenceTransformer, 
                        self.settings.ml.embedding_model
                    )
                    logger.info("Embedding model loaded successfully")
        return self.embedding_model
    
    def extract_pdf_metadata(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract metadata from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            metadata = doc.metadata
            
            return {
                "title": metadata.get("title", "").strip() or pdf_path.stem,
                "author": metadata.get("author", "").strip() or None,
                "subject": metadata.get("subject", "").strip() or None,
                "pages_count": len(doc),
                "file_size": pdf_path.stat().st_size,
            }
        except Exception as e:
            logger.error(f"Failed to extract metadata from {pdf_path}: {e}")
            return {
                "title": pdf_path.stem,
                "author": None,
                "subject": None,
                "pages_count": 0,
                "file_size": pdf_path.stat().st_size,
            }
    
    def extract_text_from_pdf(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """Extract text from PDF with page-level granularity"""
        try:
            doc = fitz.open(pdf_path)
            pages_data = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                if text.strip():
                    pages_data.append({
                        "page_number": page_num + 1,
                        "text": text.strip(),
                        "char_count": len(text),
                    })
                else:
                    logger.warning(f"No text found on page {page_num + 1} of {pdf_path}")
            
            doc.close()
            return pages_data
            
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path}: {e}")
            return []
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for change detection"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    async def process_single_pdf(
        self, 
        pdf_path: Path, 
        session: AsyncSession,
        force_reprocess: bool = False
    ) -> Optional[str]:
        """Process a single PDF file and store in database"""
        start_time = time.time()
        
        try:
            # Calculate file hash for change detection
            file_hash = self.calculate_file_hash(pdf_path)
            if not file_hash:
                return None
            
            # Check if document already exists and is up to date
            result = await session.execute(
                select(Document).where(Document.filename == pdf_path.name)
            )
            existing_doc = result.scalar_one_or_none()
            
            if existing_doc and not force_reprocess:
                if existing_doc.file_hash == file_hash and existing_doc.processing_status == "completed":
                    logger.info(f"Document {pdf_path.name} already processed and up to date")
                    return str(existing_doc.id)
                
                # Update existing document
                document = existing_doc
                document.file_hash = file_hash
                document.processing_status = "processing"
                document.error_message = None
                
                # Delete existing chunks
                await session.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == document.id).delete()
                )
            else:
                # Create new document
                metadata = self.extract_pdf_metadata(pdf_path)
                document = Document(
                    filename=pdf_path.name,
                    file_path=str(pdf_path),
                    file_hash=file_hash,
                    file_size=metadata["file_size"],
                    title=metadata["title"],
                    author=metadata["author"],
                    subject=metadata["subject"],
                    pages_count=metadata["pages_count"],
                    processing_status="processing"
                )
                session.add(document)
                await session.flush()  # Get the document ID
            
            # Extract text from PDF
            logger.info(f"Extracting text from {pdf_path.name}")
            pages_data = self.extract_text_from_pdf(pdf_path)
            
            if not pages_data:
                document.processing_status = "failed"
                document.error_message = "No text content found in PDF"
                await session.commit()
                return None
            
            # Process pages and create chunks
            all_chunks = []
            for page_data in pages_data:
                chunks = self.text_chunker.chunk_text(
                    page_data["text"],
                    page_number=page_data["page_number"]
                )
                all_chunks.extend(chunks)
            
            # Generate embeddings for all chunks
            if all_chunks:
                logger.info(f"Generating embeddings for {len(all_chunks)} chunks from {pdf_path.name}")
                embedding_model = await self.get_embedding_model()
                
                # Extract text for embedding generation
                chunk_texts = [chunk["text"] for chunk in all_chunks]
                
                # Generate embeddings in batches
                batch_size = self.settings.processing.batch_size
                embeddings = []
                
                for i in range(0, len(chunk_texts), batch_size):
                    batch_texts = chunk_texts[i:i + batch_size]
                    batch_embeddings = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: embedding_model.encode(batch_texts, show_progress_bar=False)
                    )
                    embeddings.extend(batch_embeddings)
                
                # Create chunk records
                chunk_records = []
                for chunk_data, embedding in zip(all_chunks, embeddings):
                    chunk_record = DocumentChunk(
                        document_id=document.id,
                        page_number=chunk_data["page_number"],
                        chunk_index=chunk_data["chunk_index"],
                        text_content=chunk_data["text"],
                        text_length=len(chunk_data["text"]),
                        embedding=embedding.tolist(),
                        embedding_model=self.settings.ml.embedding_model
                    )
                    chunk_records.append(chunk_record)
                
                # Batch insert chunks
                session.add_all(chunk_records)
            
            # Update document status
            document.processing_status = "completed"
            document.processed_at = asyncio.get_event_loop().time()
            await session.commit()
            
            processing_time = time.time() - start_time
            logger.info(
                f"Successfully processed {pdf_path.name}: "
                f"{len(all_chunks)} chunks in {processing_time:.2f}s"
            )
            
            return str(document.id)
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            if 'document' in locals():
                document.processing_status = "failed"
                document.error_message = str(e)
                await session.commit()
            return None
    
    async def process_pdf_directory(
        self, 
        session: AsyncSession,
        force_reprocess: bool = False
    ) -> Dict[str, Any]:
        """Process all PDFs in the configured directory"""
        pdf_dir = Path(self.settings.processing.pdf_dir)
        
        if not pdf_dir.exists():
            logger.error(f"PDF directory does not exist: {pdf_dir}")
            return {"success": False, "error": "PDF directory not found"}
        
        # Find all PDF files
        pdf_files = list(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning(f"No PDF files found in {pdf_dir}")
            return {"success": True, "processed": 0, "failed": 0, "skipped": 0}
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        # Process files
        processed = 0
        failed = 0
        skipped = 0
        
        # Use semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(self.settings.processing.max_workers)
        
        async def process_with_semaphore(pdf_path: Path) -> bool:
            async with semaphore:
                result = await self.process_single_pdf(pdf_path, session, force_reprocess)
                return result is not None
        
        # Process all files concurrently
        tasks = [process_with_semaphore(pdf_path) for pdf_path in pdf_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count results
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result:
                processed += 1
            else:
                failed += 1
        
        logger.info(f"Processing complete: {processed} processed, {failed} failed")
        
        return {
            "success": True,
            "total": len(pdf_files),
            "processed": processed,
            "failed": failed,
            "skipped": skipped
        }
    
    async def reprocess_failed_documents(self, session: AsyncSession) -> Dict[str, Any]:
        """Reprocess documents that failed processing"""
        result = await session.execute(
            select(Document).where(Document.processing_status == "failed")
        )
        failed_docs = result.scalars().all()
        
        if not failed_docs:
            return {"success": True, "reprocessed": 0}
        
        logger.info(f"Reprocessing {len(failed_docs)} failed documents")
        
        reprocessed = 0
        for doc in failed_docs:
            pdf_path = Path(doc.file_path)
            if pdf_path.exists():
                result = await self.process_single_pdf(pdf_path, session, force_reprocess=True)
                if result:
                    reprocessed += 1
        
        return {"success": True, "reprocessed": reprocessed}