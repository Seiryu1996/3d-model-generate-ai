"""
Logging configuration for the TRELLIS API.
"""
import logging
import logging.config
import sys
from typing import Dict, Any

import structlog
from google.cloud import logging as cloud_logging

from .config import get_settings


def setup_logging() -> None:
    """Set up structured logging with Google Cloud Logging integration."""
    settings = get_settings()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.is_production() else structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
            },
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "json" if settings.is_production() else "console",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": "DEBUG" if settings.DEBUG else "INFO",
                "propagate": True,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "WARNING" if settings.is_production() else "INFO",
                "propagate": False,
            },
        },
    }
    
    # Add Google Cloud Logging in production
    if settings.is_production() and settings.GOOGLE_CLOUD_PROJECT:
        try:
            client = cloud_logging.Client(project=settings.GOOGLE_CLOUD_PROJECT)
            client.setup_logging()
            
            # Add cloud logging handler
            logging_config["handlers"]["cloud"] = {
                "class": "google.cloud.logging.handlers.CloudLoggingHandler",
                "client": client,
                "formatter": "json",
            }
            
            # Update root logger to use cloud handler
            logging_config["loggers"][""]["handlers"].append("cloud")
            
        except Exception as e:
            # Fallback to console logging if cloud logging fails
            logger = structlog.get_logger()
            logger.warning("Failed to set up Google Cloud Logging", error=str(e))
    
    logging.config.dictConfig(logging_config)


def get_logger(name: str = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LoggingMiddleware:
    """Middleware for request/response logging."""
    
    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware.logging")
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request_id = scope.get("headers", {}).get("x-request-id", "unknown")
            
            # Log request start
            self.logger.info(
                "Request started",
                method=scope["method"],
                path=scope["path"],
                request_id=request_id,
            )
            
            # Process request
            await self.app(scope, receive, send)
            
            # Note: Response logging would need to be handled differently
            # due to ASGI architecture limitations
        else:
            await self.app(scope, receive, send)