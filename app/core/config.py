"""
Configuration management using Pydantic settings.
Supports environment variables and .env files.
"""
from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
import os
import json


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    model_config = {"env_prefix": "DATABASE_", "extra": "ignore"}
    
    url: str = Field(default="postgresql+asyncpg://pdf_user:pdf_password@localhost:5433/pdf_miner")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20)
    max_overflow: int = Field(default=0)
    pool_timeout: int = Field(default=30)
    pool_recycle: int = Field(default=3600)


class RedisSettings(BaseSettings):
    """Redis configuration"""
    model_config = {"env_prefix": "REDIS_"}
    
    url: str = Field(default="redis://localhost:6379/0")
    max_connections: int = Field(default=20)
    encoding: str = Field(default="utf-8")
    decode_responses: bool = Field(default=True)
    socket_timeout: int = Field(default=5)
    socket_connect_timeout: int = Field(default=5)
    health_check_interval: int = Field(default=30)


class MLSettings(BaseSettings):
    """Machine Learning model configuration"""
    model_config = {"env_prefix": ""}
    
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    qa_model: str = Field(default="deepset/roberta-base-squad2")
    embedding_dimension: int = Field(default=384)
    max_chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=50)
    similarity_threshold: float = Field(default=0.7)
    top_k_results: int = Field(default=5)


class ProcessingSettings(BaseSettings):
    """PDF processing configuration"""
    model_config = {"env_prefix": ""}
    
    pdf_dir: str = Field(default="data/pdfs")
    max_file_size_mb: int = Field(default=100)
    max_workers: int = Field(default=4)
    batch_size: int = Field(default=32)
    processing_timeout: int = Field(default=300)


class APISettings(BaseSettings):
    """API configuration"""
    model_config = {"env_prefix": "API_"}
    
    title: str = Field(default="PDF Knowledge Miner API")
    description: str = Field(default="Semantic search API for PDF documents")
    version: str = Field(default="2.0.0")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    reload: bool = Field(default=False)
    workers: int = Field(default=1)
    max_request_size: int = Field(default=104857600)  # 100MB


class SecuritySettings(BaseSettings):
    """Security configuration"""
    model_config = {"env_prefix": ""}
    
    secret_key: str = Field(default="your-secret-key-change-in-production")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    cors_origins: list[str] = Field(default=["*"])
    cors_methods: list[str] = Field(default=["*"])
    cors_headers: list[str] = Field(default=["*"])


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    model_config = {"env_prefix": "LOGGING_"}
    
    level: str = Field(default="INFO")
    format: str = Field(default="json")
    file_path: Optional[str] = Field(default=None)
    max_file_size_mb: int = Field(default=10)
    backup_count: int = Field(default=5)


class MonitoringSettings(BaseSettings):
    """Monitoring configuration"""
    model_config = {"env_prefix": ""}
    
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=8001)
    sentry_dsn: Optional[str] = Field(default=None)
    health_check_interval: int = Field(default=30)


class Settings(BaseSettings):
    """Main settings class"""
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
    
    # Environment
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    
    # Component settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ml: MLSettings = Field(default_factory=MLSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    api: APISettings = Field(default_factory=APISettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()