"""
Health check endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, status
import structlog

from ...models.api import HealthResponse
from ...utils.config import get_settings
from ...utils.storage_adapter import get_storage_manager

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check the health status of the API and its dependencies."
)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    storage_manager = get_storage_manager()
    
    # Base API service is always healthy if we reach this point
    services = {
        "api": "healthy"
    }
    
    # Check storage services (GCP or local)
    try:
        storage_health = await storage_manager.health_check()
        services.update(storage_health)
    except Exception as e:
        logger.warning("Storage health check failed", error=str(e))
        services["storage"] = "unhealthy"
    
    overall_status = "healthy" if all(
        status == "healthy" for status in services.values()
    ) else "degraded"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version="1.0.0",
        services=services
    )