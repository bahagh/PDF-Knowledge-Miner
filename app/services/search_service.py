"""
High-performance search service with vector similarity search and caching.
Provides semantic search capabilities with QA integration.
"""
import asyncio
import hashlib
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import pipeline
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.orm import joinedload
from app.core.config import get_settings
from app.models.database import Document, DocumentChunk, SearchQuery, SearchResult
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class SearchService:
    """Advanced search service with vector similarity and caching"""
    
    def __init__(self, cache_service: CacheService):
        self.settings = get_settings()
        self.cache = cache_service
        self.embedding_model = None
        self.qa_pipeline = None
        self._model_lock = asyncio.Lock()
        self._qa_lock = asyncio.Lock()
    
    async def get_embedding_model(self) -> SentenceTransformer:
        """Get or initialize the embedding model (thread-safe)"""
        if self.embedding_model is None:
            async with self._model_lock:
                if self.embedding_model is None:
                    logger.info(f"Loading embedding model: {self.settings.ml.embedding_model}")
                    loop = asyncio.get_event_loop()
                    self.embedding_model = await loop.run_in_executor(
                        None,
                        SentenceTransformer,
                        self.settings.ml.embedding_model
                    )
                    logger.info("Embedding model loaded successfully")
        return self.embedding_model
    
    async def get_qa_pipeline(self):
        """Get or initialize the QA pipeline (thread-safe)"""
        if self.qa_pipeline is None:
            async with self._qa_lock:
                if self.qa_pipeline is None:
                    logger.info(f"Loading QA model: {self.settings.ml.qa_model}")
                    loop = asyncio.get_event_loop()
                    self.qa_pipeline = await loop.run_in_executor(
                        None,
                        lambda: pipeline(
                            "question-answering",
                            model=self.settings.ml.qa_model,
                            tokenizer=self.settings.ml.qa_model
                        )
                    )
                    logger.info("QA model loaded successfully")
        return self.qa_pipeline
    
    def _hash_query(self, query: str, **kwargs) -> str:
        """Generate hash for query caching"""
        query_string = f"{query}_{kwargs.get('top_k', 5)}_{kwargs.get('similarity_threshold', 0.7)}"
        return hashlib.md5(query_string.encode()).hexdigest()
    
    async def _generate_query_embedding(self, query: str) -> np.ndarray:
        """Generate embedding for search query with caching"""
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        # Try to get from cache first
        cached_embedding = await self.cache.get_embedding(query_hash)
        if cached_embedding is not None:
            return cached_embedding
        
        # Generate new embedding
        model = await self.get_embedding_model()
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: model.encode([query], show_progress_bar=False)
        )
        
        embedding_array = np.array(embedding[0])
        
        # Cache the embedding
        await self.cache.set_embedding(query_hash, embedding_array)
        
        return embedding_array
    
    async def semantic_search(
        self,
        session: AsyncSession,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
        document_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform semantic search across document chunks.
        
        Args:
            session: Database session
            query: Search query text
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            document_ids: Limit search to specific documents
            user_id: User ID for tracking
            session_id: Session ID for tracking
            ip_address: IP address for tracking
            user_agent: User agent for tracking
            
        Returns:
            Search results with metadata
        """
        start_time = time.time()
        
        # Use default values from settings
        top_k = top_k or self.settings.ml.top_k_results
        similarity_threshold = similarity_threshold or self.settings.ml.similarity_threshold
        
        # Check cache first
        query_hash = self._hash_query(
            query, 
            top_k=top_k, 
            similarity_threshold=similarity_threshold,
            document_ids=document_ids
        )
        
        cached_results = await self.cache.get_search_results(query_hash)
        if cached_results:
            logger.info(f"Returning cached results for query: {query[:50]}...")
            return cached_results
        
        try:
            # Generate query embedding
            query_embedding = await self._generate_query_embedding(query)
            
            # Create search query record
            search_query = SearchQuery(
                query_text=query,
                query_embedding=query_embedding.tolist(),
                embedding_model=self.settings.ml.embedding_model,
                similarity_threshold=similarity_threshold,
                top_k=top_k,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            session.add(search_query)
            await session.flush()  # Get query ID
            
            # Build vector similarity query
            # Using cosine similarity with pgvector
            base_query = select(
                DocumentChunk,
                Document,
                (1 - DocumentChunk.embedding.cosine_distance(query_embedding.tolist())).label('similarity')
            ).join(Document).where(
                DocumentChunk.embedding.is_not(None),
                (1 - DocumentChunk.embedding.cosine_distance(query_embedding.tolist())) >= similarity_threshold
            )
            
            # Filter by document IDs if provided
            if document_ids:
                base_query = base_query.where(Document.id.in_(document_ids))
            
            # Order by similarity and limit results
            query_stmt = base_query.order_by(
                (1 - DocumentChunk.embedding.cosine_distance(query_embedding.tolist())).desc()
            ).limit(top_k)
            
            # Execute search
            result = await session.execute(query_stmt)
            search_results = result.all()
            
            # Process results
            results = []
            search_result_records = []
            
            for rank, (chunk, document, similarity) in enumerate(search_results):
                result_data = {
                    "chunk_id": str(chunk.id),
                    "document_id": str(document.id),
                    "document_filename": document.filename,
                    "document_title": document.title,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "text_content": chunk.text_content,
                    "similarity_score": float(similarity),
                    "rank": rank + 1
                }
                
                results.append(result_data)
                
                # Create search result record
                search_result_record = SearchResult(
                    query_id=search_query.id,
                    chunk_id=chunk.id,
                    similarity_score=float(similarity),
                    rank_position=rank + 1
                )
                search_result_records.append(search_result_record)
            
            # Add search result records
            session.add_all(search_result_records)
            
            # Update search query with results count and processing time
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            search_query.results_count = len(results)
            search_query.processing_time_ms = processing_time
            
            await session.commit()
            
            # Prepare final response
            response = {
                "query": query,
                "results": results,
                "total_results": len(results),
                "processing_time_ms": processing_time,
                "similarity_threshold": similarity_threshold,
                "top_k": top_k,
                "query_id": str(search_query.id)
            }
            
            # Cache results
            await self.cache.set_search_results(query_hash, response)
            
            logger.info(
                f"Search completed: {len(results)} results in {processing_time:.2f}ms "
                f"for query: {query[:50]}..."
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Search error for query '{query}': {e}")
            raise
    
    async def search_with_qa(
        self,
        session: AsyncSession,
        query: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform semantic search and extract answers using QA model.
        
        Args:
            session: Database session
            query: Search query text
            **kwargs: Additional search parameters
            
        Returns:
            Search results with QA answers
        """
        # Perform semantic search
        search_results = await self.semantic_search(session, query, **kwargs)
        
        if not search_results["results"]:
            return search_results
        
        try:
            # Get QA pipeline
            qa_pipeline = await self.get_qa_pipeline()
            
            # Process top results with QA
            qa_results = []
            
            for result in search_results["results"][:3]:  # Limit QA to top 3 results
                try:
                    # Run QA in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    qa_answer = await loop.run_in_executor(
                        None,
                        lambda: qa_pipeline(
                            question=query,
                            context=result["text_content"]
                        )
                    )
                    
                    result["qa_answer"] = qa_answer.get("answer", "")
                    result["qa_confidence"] = qa_answer.get("score", 0.0)
                    qa_results.append(result)
                    
                except Exception as e:
                    logger.error(f"QA processing error: {e}")
                    result["qa_answer"] = "Error processing answer"
                    result["qa_confidence"] = 0.0
                    qa_results.append(result)
            
            # Update search results in database with QA answers
            for result in qa_results:
                if "qa_answer" in result and result["qa_answer"]:
                    await session.execute(
                        select(SearchResult).where(
                            SearchResult.query_id == search_results["query_id"],
                            SearchResult.chunk_id == result["chunk_id"]
                        ).update({
                            SearchResult.qa_answer: result["qa_answer"],
                            SearchResult.qa_confidence: result["qa_confidence"]
                        })
                    )
            
            await session.commit()
            
            # Update response
            search_results["results"] = qa_results
            search_results["has_qa_answers"] = True
            
        except Exception as e:
            logger.error(f"QA processing error: {e}")
            search_results["qa_error"] = str(e)
        
        return search_results
    
    async def get_similar_documents(
        self,
        session: AsyncSession,
        document_id: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Find documents similar to a given document"""
        try:
            # Get document chunks
            result = await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .where(DocumentChunk.embedding.is_not(None))
            )
            chunks = result.scalars().all()
            
            if not chunks:
                return []
            
            # Calculate average embedding for the document
            embeddings = [np.array(chunk.embedding) for chunk in chunks]
            avg_embedding = np.mean(embeddings, axis=0)
            
            # Find similar documents
            similar_query = select(
                Document,
                func.avg(1 - DocumentChunk.embedding.cosine_distance(avg_embedding.tolist())).label('avg_similarity')
            ).join(DocumentChunk).where(
                Document.id != document_id,
                DocumentChunk.embedding.is_not(None)
            ).group_by(Document.id).order_by(
                func.avg(1 - DocumentChunk.embedding.cosine_distance(avg_embedding.tolist())).desc()
            ).limit(top_k)
            
            result = await session.execute(similar_query)
            similar_docs = result.all()
            
            return [
                {
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "title": doc.title,
                    "similarity_score": float(similarity),
                    "pages_count": doc.pages_count,
                    "file_size": doc.file_size
                }
                for doc, similarity in similar_docs
            ]
            
        except Exception as e:
            logger.error(f"Error finding similar documents: {e}")
            return []
    
    async def get_search_analytics(
        self,
        session: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get search analytics and statistics"""
        try:
            # Get analytics from cache first
            cache_key = f"analytics_{days}d"
            cached_analytics = await self.cache.get_stats(cache_key)
            if cached_analytics:
                return cached_analytics
            
            # Calculate date range
            from datetime import datetime, timedelta
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Query analytics
            analytics_query = select(
                func.count(SearchQuery.id).label('total_searches'),
                func.avg(SearchQuery.processing_time_ms).label('avg_processing_time'),
                func.avg(SearchQuery.results_count).label('avg_results_count'),
                func.count(func.distinct(SearchQuery.session_id)).label('unique_sessions')
            ).where(SearchQuery.created_at >= start_date)
            
            result = await session.execute(analytics_query)
            stats = result.first()
            
            # Top queries
            top_queries_query = select(
                SearchQuery.query_text,
                func.count(SearchQuery.id).label('frequency')
            ).where(
                SearchQuery.created_at >= start_date
            ).group_by(SearchQuery.query_text).order_by(
                func.count(SearchQuery.id).desc()
            ).limit(10)
            
            result = await session.execute(top_queries_query)
            top_queries = [
                {"query": query, "frequency": freq}
                for query, freq in result.all()
            ]
            
            analytics = {
                "period_days": days,
                "total_searches": stats.total_searches or 0,
                "avg_processing_time_ms": float(stats.avg_processing_time or 0),
                "avg_results_count": float(stats.avg_results_count or 0),
                "unique_sessions": stats.unique_sessions or 0,
                "top_queries": top_queries,
                "generated_at": datetime.utcnow().isoformat()
            }
            
            # Cache analytics
            await self.cache.set_stats(cache_key, analytics)
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting search analytics: {e}")
            return {"error": str(e)}