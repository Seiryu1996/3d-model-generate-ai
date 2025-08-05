"""
Health check endpoints.
"""
from datetime import datetime
from fastapi import APIRouter, status
import structlog

from ...models.api import HealthResponse, MetricsResponse, SystemMetrics, JobMetrics
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


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="System Metrics",
    description="Get system and job processing metrics for monitoring."
)
async def get_metrics() -> MetricsResponse:
    """System metrics endpoint."""
    import psutil
    import time
    
    from ...repositories.job_repository import get_job_repository
    from ...models.base import JobStatus
    
    job_repo = get_job_repository()
    
    # Collect system metrics
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    boot_time = psutil.boot_time()
    uptime = time.time() - boot_time
    
    system_metrics = SystemMetrics(
        cpu_usage=cpu_usage,
        memory_usage=memory.percent,
        disk_usage=disk.percent,
        uptime_seconds=uptime
    )
    
    # Collect job metrics
    try:
        # Get job counts by status
        total_jobs = await job_repo.count_jobs()
        pending_jobs = await job_repo.count_jobs_by_status(JobStatus.PENDING)
        processing_jobs = await job_repo.count_jobs_by_status(JobStatus.PROCESSING)
        completed_jobs = await job_repo.count_jobs_by_status(JobStatus.COMPLETED)
        failed_jobs = await job_repo.count_jobs_by_status(JobStatus.FAILED)
        
        # Calculate average processing time for completed jobs
        avg_processing_time = await job_repo.get_average_processing_time()
        
        job_metrics = JobMetrics(
            total_jobs=total_jobs,
            pending_jobs=pending_jobs,
            processing_jobs=processing_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            average_processing_time=avg_processing_time or 0.0
        )
        
    except Exception as e:
        logger.warning("Failed to collect job metrics", error=str(e))
        # Fallback to default values
        job_metrics = JobMetrics(
            total_jobs=0,
            pending_jobs=0,
            processing_jobs=0,
            completed_jobs=0,
            failed_jobs=0,
            average_processing_time=0.0
        )
    
    return MetricsResponse(
        system=system_metrics,
        jobs=job_metrics
    )
