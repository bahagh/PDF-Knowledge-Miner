"""
Database connection and session management.
Uses async SQLAlchemy with connection pooling and health checks.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text
from app.core.config import get_settings
from app.models.database import Base

logger = logging.getLogger(__name__)


class Database:
    """Database manager with connection pooling and health checks"""
    
    def __init__(self):
        self.settings = get_settings().database
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables"""
        if self._initialized:
            return
            
        try:
            # Create async engine with connection pooling
            self.engine = create_async_engine(
                self.settings.url,
                echo=self.settings.echo,
                pool_size=self.settings.pool_size,
                max_overflow=self.settings.max_overflow,
                pool_timeout=self.settings.pool_timeout,
                pool_recycle=self.settings.pool_recycle,
                pool_pre_ping=True,  # Validate connections before use
            )
            
            # Create session factory
            self.SessionLocal = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
            
            # Create tables and enable pgvector extension
            await self._create_tables()
            
            # Test connection
            await self.health_check()
            
            self._initialized = True
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _create_tables(self) -> None:
        """Create database tables and enable pgvector extension"""
        async with self.engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database tables created/verified")
    
    async def close(self) -> None:
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup"""
        if not self._initialized:
            await self.initialize()
            
        async with self.SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Unexpected error in database session: {e}")
                raise
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            if not self._initialized:
                return False
                
            async with self.SessionLocal() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def get_stats(self) -> dict:
        """Get database statistics"""
        try:
            async with self.session() as session:
                # Get table sizes
                result = await session.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_tuples,
                        n_dead_tup as dead_tuples
                    FROM pg_stat_user_tables
                    WHERE schemaname = 'public'
                """))
                
                tables = {}
                for row in result:
                    tables[row.tablename] = {
                        "inserts": row.inserts,
                        "updates": row.updates,
                        "deletes": row.deletes,
                        "live_tuples": row.live_tuples,
                        "dead_tuples": row.dead_tuples,
                    }
                
                # Get connection pool stats
                pool_stats = {
                    "size": self.engine.pool.size(),
                    "checked_in": self.engine.pool.checkedin(),
                    "checked_out": self.engine.pool.checkedout(),
                    "overflow": self.engine.pool.overflow(),
                    "invalid": self.engine.pool.invalid(),
                }
                
                return {
                    "tables": tables,
                    "pool": pool_stats,
                    "healthy": True,
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {"healthy": False, "error": str(e)}


# Global database instance
db = Database()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session"""
    async with db.session() as session:
        yield session


async def init_db() -> None:
    """Initialize database - called at application startup"""
    await db.initialize()


async def close_db() -> None:
    """Close database connections - called at application shutdown"""
    await db.close()