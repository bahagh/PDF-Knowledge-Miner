"""
Logging configuration with structured logging and proper formatting.
"""
import logging
import logging.config
import sys
from pathlib import Path
from typing import Dict, Any
import structlog
from app.core.config import get_settings


def setup_logging() -> None:
    """Setup structured logging configuration"""
    settings = get_settings()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.logging.format == "json" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    log_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "format": "%(message)s",
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            },
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.logging.level,
                "formatter": "json" if settings.logging.format == "json" else "standard",
                "stream": sys.stdout,
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": settings.logging.level,
                "propagate": False,
            },
            "app": {
                "handlers": ["console"],
                "level": settings.logging.level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "sqlalchemy": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
        "root": {
            "level": settings.logging.level,
            "handlers": ["console"],
        },
    }
    
    # Add file handler if file path is specified
    if settings.logging.file_path:
        log_file = Path(settings.logging.file_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        log_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": settings.logging.level,
            "formatter": "json" if settings.logging.format == "json" else "standard",
            "filename": str(log_file),
            "maxBytes": settings.logging.max_file_size_mb * 1024 * 1024,
            "backupCount": settings.logging.backup_count,
            "encoding": "utf-8",
        }
        
        # Add file handler to all loggers
        for logger_name in log_config["loggers"]:
            log_config["loggers"][logger_name]["handlers"].append("file")
        
        log_config["root"]["handlers"].append("file")
    
    logging.config.dictConfig(log_config)
    
    # Set up Sentry if DSN is provided
    if settings.monitoring.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
            from sentry_sdk.integrations.redis import RedisIntegration
            
            sentry_sdk.init(
                dsn=settings.monitoring.sentry_dsn,
                environment=settings.environment,
                integrations=[
                    FastApiIntegration(auto_enabling_integrations=True),
                    SqlalchemyIntegration(),
                    RedisIntegration(),
                ],
                traces_sample_rate=0.1,
                send_default_pii=False,
            )
            
            logging.info("Sentry integration initialized")
            
        except ImportError:
            logging.warning("Sentry SDK not installed, skipping Sentry integration")
        except Exception as e:
            logging.error(f"Failed to initialize Sentry: {e}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name"""
    return logging.getLogger(name)