"""
Command-line interface for the PDF Knowledge Miner.
"""
import asyncio
import click
import logging
from pathlib import Path
from app.core.config import get_settings
from app.core.database import init_db, db
from app.core.logging_config import setup_logging
from app.services.pdf_processor import PDFProcessor
from app.services.cache_service import init_cache
from app.services.search_service import SearchService

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@click.group()
def main():
    """PDF Knowledge Miner CLI"""
    pass


@main.command()
@click.option('--query', '-q', required=True, help='Search query')
@click.option('--top-k', '-k', default=5, help='Number of results to return')
@click.option('--threshold', '-t', default=0.7, help='Similarity threshold')
@click.option('--qa', is_flag=True, help='Include question answering')
def search(query: str, top_k: int, threshold: float, qa: bool):
    """Search documents from command line"""
    asyncio.run(_search(query, top_k, threshold, qa))


async def _search(query: str, top_k: int, threshold: float, qa: bool):
    """Async search implementation"""
    try:
        # Initialize services
        await init_db()
        await init_cache()
        
        from app.services.cache_service import get_cache
        cache_service = await get_cache()
        search_service = SearchService(cache_service)
        
        async with db.session() as session:
            if qa:
                results = await search_service.search_with_qa(
                    session=session,
                    query=query,
                    top_k=top_k,
                    similarity_threshold=threshold
                )
            else:
                results = await search_service.semantic_search(
                    session=session,
                    query=query,
                    top_k=top_k,
                    similarity_threshold=threshold
                )
            
            # Display results
            click.echo(f"\nQuery: {query}")
            click.echo(f"Results: {results['total_results']}")
            click.echo(f"Processing time: {results['processing_time_ms']:.2f}ms\n")
            
            for i, result in enumerate(results['results'], 1):
                click.echo(f"{i}. {result['document_filename']} (Page {result['page_number']})")
                click.echo(f"   Similarity: {result['similarity_score']:.3f}")
                click.echo(f"   Text: {result['text_content'][:200]}...")
                
                if qa and 'qa_answer' in result:
                    click.echo(f"   Answer: {result['qa_answer']}")
                    click.echo(f"   Confidence: {result['qa_confidence']:.3f}")
                
                click.echo()
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        click.echo(f"Error: {e}")


@main.command()
@click.option('--force', is_flag=True, help='Force reprocessing of existing documents')
def process(force: bool):
    """Process all PDF documents"""
    asyncio.run(_process(force))


async def _process(force: bool):
    """Async process implementation"""
    try:
        await init_db()
        
        pdf_processor = PDFProcessor()
        
        async with db.session() as session:
            result = await pdf_processor.process_pdf_directory(
                session=session,
                force_reprocess=force
            )
            
            click.echo(f"Processing completed:")
            click.echo(f"  Total: {result['total']}")
            click.echo(f"  Processed: {result['processed']}")
            click.echo(f"  Failed: {result['failed']}")
            click.echo(f"  Skipped: {result['skipped']}")
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        click.echo(f"Error: {e}")


@main.command()
def serve():
    """Start the web server"""
    import uvicorn
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        workers=settings.api.workers,
        log_level=settings.logging.level.lower(),
    )


@main.command()
def init_database():
    """Initialize the database"""
    asyncio.run(_init_database())


async def _init_database():
    """Initialize database tables"""
    try:
        await init_db()
        click.echo("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        click.echo(f"Error: {e}")


@main.command()
@click.option('--cache-type', help='Type of cache to clear (embeddings, search, documents, all)')
def clear_cache(cache_type: str):
    """Clear cache"""
    asyncio.run(_clear_cache(cache_type))


async def _clear_cache(cache_type: str):
    """Clear cache implementation"""
    try:
        await init_cache()
        
        from app.services.cache_service import get_cache
        cache_service = await get_cache()
        
        cleared = await cache_service.clear_cache(cache_type)
        
        click.echo(f"Cache cleared: {cache_type or 'all'}")
        click.echo(f"Keys cleared: {cleared}")
        
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        click.echo(f"Error: {e}")


@main.command()
def status():
    """Show system status"""
    asyncio.run(_status())


async def _status():
    """Show system status implementation"""
    try:
        # Check database
        await init_db()
        db_healthy = await db.health_check()
        
        # Check cache
        await init_cache()
        from app.services.cache_service import get_cache
        cache_service = await get_cache()
        cache_healthy = await cache_service.health_check()
        
        # Get stats
        async with db.session() as session:
            from sqlalchemy import select, func
            from app.models.database import Document, DocumentChunk, SearchQuery
            
            doc_count_result = await session.execute(select(func.count(Document.id)))
            doc_count = doc_count_result.scalar()
            
            chunk_count_result = await session.execute(select(func.count(DocumentChunk.id)))
            chunk_count = chunk_count_result.scalar()
            
            search_count_result = await session.execute(select(func.count(SearchQuery.id)))
            search_count = search_count_result.scalar()
        
        click.echo("System Status:")
        click.echo(f"  Database: {'✓' if db_healthy else '✗'}")
        click.echo(f"  Cache: {'✓' if cache_healthy else '✗'}")
        click.echo(f"\nStatistics:")
        click.echo(f"  Documents: {doc_count}")
        click.echo(f"  Chunks: {chunk_count}")
        click.echo(f"  Searches: {search_count}")
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        click.echo(f"Error: {e}")


if __name__ == '__main__':
    main()