"""
Worker endpoints for processing tasks from the queue.
"""
from fastapi import APIRouter, HTTPException, status, Request, Header
from typing import Dict, Any, Optional
import structlog

from ...services.queue_service import get_queue_service, QueueServiceError
from ...services.job_service import get_job_service, JobServiceError
from ...services.worker_service import get_worker_service
from ...models.base import BaseResponse
from ...utils.config import get_settings

router = APIRouter()
logger = structlog.get_logger(__name__)


async def verify_worker_token(authorization: Optional[str] = Header(None)) -> str:
    """Verify worker authentication token."""
    settings = get_settings()
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # Simple token validation - in production, use proper JWT or API key validation
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format"
        )
    
    token = authorization.replace("Bearer ", "")
    
    # TODO: Implement proper token validation
    # For now, accept any non-empty token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    return token


@router.post(
    "/worker/process",
    response_model=BaseResponse,
    summary="Process Task",
    description="Process a task from the queue (called by workers)."
)
async def process_task(
    payload: Dict[str, Any],
    worker_token: str = Header(alias="authorization", default=None)
) -> BaseResponse:
    """Process a task from the queue."""
    # Verify worker authentication
    await verify_worker_token(worker_token)
    
    queue_service = get_queue_service()
    
    try:
        logger.info(
            "Received task processing request",
            job_id=payload.get('job_id'),
            job_type=payload.get('job_type'),
            processing_type=payload.get('processing_type')
        )
        
        # Process the task webhook
        response = await queue_service.process_task_webhook(payload)
        
        logger.info(
            "Task processing completed",
            job_id=payload.get('job_id'),
            response=response
        )
        
        return BaseResponse(
            success=True,
            message="Task accepted for processing"
        )
        
    except QueueServiceError as e:
        logger.error(
            "Queue service error during task processing",
            job_id=payload.get('job_id'),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Queue service error: {e}"
        )
    except Exception as e:
        logger.error(
            "Unexpected error during task processing",
            job_id=payload.get('job_id'),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/worker/progress/{job_id}",
    response_model=BaseResponse,
    summary="Update Job Progress",
    description="Update job progress (called by workers)."
)
async def update_job_progress(
    job_id: str,
    progress_data: Dict[str, Any],
    worker_token: str = Header(alias="authorization", default=None)
) -> BaseResponse:
    """Update job progress."""
    # Verify worker authentication
    worker_id = await verify_worker_token(worker_token)
    
    job_service = get_job_service()
    
    try:
        progress = progress_data.get('progress', 0.0)
        
        if not 0 <= progress <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Progress must be between 0 and 1"
            )
        
        success = await job_service.update_job_progress(job_id, progress, worker_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or could not be updated"
            )
        
        logger.info(
            "Job progress updated by worker",
            job_id=job_id,
            progress=progress,
            worker_id=worker_id
        )
        
        return BaseResponse(
            success=True,
            message="Progress updated successfully"
        )
        
    except JobServiceError as e:
        logger.error(
            "Job service error during progress update",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job service error: {e}"
        )
    except Exception as e:
        logger.error(
            "Unexpected error during progress update",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/worker/complete/{job_id}",
    response_model=BaseResponse,
    summary="Mark Job Complete",
    description="Mark job as completed with output files (called by workers)."
)
async def complete_job(
    job_id: str,
    completion_data: Dict[str, Any],
    worker_token: str = Header(alias="authorization", default=None)
) -> BaseResponse:
    """Mark job as completed."""
    # Verify worker authentication
    worker_id = await verify_worker_token(worker_token)
    
    job_service = get_job_service()
    
    try:
        from ...models.job import JobOutputFile
        
        # Parse output files
        output_files_data = completion_data.get('output_files', [])
        output_files = []
        
        for file_data in output_files_data:
            output_file = JobOutputFile(
                format=file_data.get('format'),
                url=file_data.get('url'),
                size_bytes=file_data.get('size_bytes'),
                filename=file_data.get('filename')
            )
            output_files.append(output_file)
        
        success = await job_service.mark_job_completed(job_id, output_files, worker_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or could not be completed"
            )
        
        logger.info(
            "Job completed by worker",
            job_id=job_id,
            output_files_count=len(output_files),
            worker_id=worker_id
        )
        
        return BaseResponse(
            success=True,
            message="Job completed successfully"
        )
        
    except JobServiceError as e:
        logger.error(
            "Job service error during job completion",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job service error: {e}"
        )
    except Exception as e:
        logger.error(
            "Unexpected error during job completion",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/worker/fail/{job_id}",
    response_model=BaseResponse,
    summary="Mark Job Failed",
    description="Mark job as failed with error message (called by workers)."
)
async def fail_job(
    job_id: str,
    failure_data: Dict[str, Any],
    worker_token: str = Header(alias="authorization", default=None)
) -> BaseResponse:
    """Mark job as failed."""
    # Verify worker authentication
    worker_id = await verify_worker_token(worker_token)
    
    job_service = get_job_service()
    queue_service = get_queue_service()
    
    try:
        error_message = failure_data.get('error_message', 'Unknown error')
        retry = failure_data.get('retry', True)
        
        # Handle the failure through queue service (includes retry logic)
        handled = await queue_service.handle_task_failure(job_id, error_message, retry)
        
        logger.info(
            "Job failure handled by worker",
            job_id=job_id,
            error_message=error_message,
            retry=retry,
            handled=handled,
            worker_id=worker_id
        )
        
        return BaseResponse(
            success=True,
            message="Job failure handled successfully"
        )
        
    except QueueServiceError as e:
        logger.error(
            "Queue service error during job failure",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Queue service error: {e}"
        )
    except Exception as e:
        logger.error(
            "Unexpected error during job failure handling",
            job_id=job_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/worker/queue/stats",
    summary="Get Queue Statistics",
    description="Get queue statistics (called by monitoring systems)."
)
async def get_queue_stats(
    worker_token: str = Header(alias="authorization", default=None)
) -> Dict[str, Any]:
    """Get queue statistics."""
    # Verify worker authentication
    await verify_worker_token(worker_token)
    
    queue_service = get_queue_service()
    
    try:
        stats = await queue_service.get_queue_stats()
        
        logger.info("Queue stats requested", stats=stats)
        
        return {
            'success': True,
            'data': stats
        }
        
    except QueueServiceError as e:
        logger.error("Queue service error during stats retrieval", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Queue service error: {e}"
        )
    except Exception as e:
        logger.error("Unexpected error during stats retrieval", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/worker/health",
    summary="Worker Health Check",
    description="Check worker service health and model status."
)
async def worker_health_check(
    worker_token: str = Header(alias="authorization", default=None)
) -> Dict[str, Any]:
    """Check worker service health."""
    # Verify worker authentication
    await verify_worker_token(worker_token)
    
    worker_service = get_worker_service()
    
    try:
        health_info = await worker_service.health_check()
        
        logger.info("Worker health check performed", health_info=health_info)
        
        return health_info
        
    except Exception as e:
        logger.error("Worker health check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {e}"
        )


@router.get(
    "/worker/status",
    summary="Worker Processing Status",
    description="Get current worker processing status and statistics."
)
async def worker_processing_status(
    worker_token: str = Header(alias="authorization", default=None)
) -> Dict[str, Any]:
    """Get worker processing status."""
    # Verify worker authentication
    await verify_worker_token(worker_token)
    
    worker_service = get_worker_service()
    
    try:
        status_info = worker_service.get_processing_status()
        
        logger.info("Worker status requested", status_info=status_info)
        
        return {
            'success': True,
            'data': status_info
        }
        
    except Exception as e:
        logger.error("Worker status check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status check failed: {e}"
        )