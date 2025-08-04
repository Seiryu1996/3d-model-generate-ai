"""
Job management endpoints.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
import structlog

from ...models.api import (
    JobStatusResponse, JobResultResponse, JobListResponse, 
    DeleteJobResponse, JobSummaryResponse
)
from ...models.base import JobStatus
from ...services.job_service import get_job_service, JobServiceError, JobNotFoundError, JobAccessDeniedError

router = APIRouter()
logger = structlog.get_logger(__name__)


async def get_current_user_id() -> str:
    """Get current user ID from authentication."""
    # TODO: Implement proper authentication
    return "anonymous"


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get Job Status",
    description="Get the current status and progress of a job."
)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id)
) -> JobStatusResponse:
    """Get job status."""
    job_service = get_job_service()
    
    try:
        job = await job_service.get_job_status(job_id, user_id)
        
        return JobStatusResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            processing_time_seconds=job.processing_time_seconds,
            error_message=job.error_message
        )
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    except JobAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), job_id=job_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get Job Result",
    description="Get the result files of a completed job."
)
async def get_job_result(
    job_id: str,
    user_id: str = Depends(get_current_user_id)
) -> JobResultResponse:
    """Get job result."""
    job_service = get_job_service()
    
    try:
        job = await job_service.get_job_result(job_id, user_id)
        
        return JobResultResponse(
            job_id=job.job_id,
            status=job.status,
            output_files=job.output_files,
            processing_time_seconds=job.processing_time_seconds,
            error_message=job.error_message
        )
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    except JobAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), job_id=job_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/jobs/{job_id}",
    response_model=DeleteJobResponse,
    summary="Delete Job",
    description="Cancel or delete a job and clean up its resources."
)
async def delete_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id)
) -> DeleteJobResponse:
    """Delete or cancel a job."""
    job_service = get_job_service()
    
    try:
        success = await job_service.delete_job(job_id, user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete job"
            )
        
        return DeleteJobResponse(
            job_id=job_id,
            message="Job deleted successfully"
        )
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    except JobAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), job_id=job_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List Jobs",
    description="Get a list of jobs for the current user."
)
async def list_jobs(
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[JobStatus] = Query(None, description="Filter by job status")
) -> JobListResponse:
    """List jobs for the current user."""
    job_service = get_job_service()
    
    try:
        result = await job_service.list_user_jobs(user_id, page, page_size, status_filter)
        
        # Convert job summaries to response format
        job_responses = []
        for job_summary in result['jobs']:
            job_response = JobSummaryResponse(
                job_id=job_summary.job_id,
                job_type=job_summary.job_type,
                status=job_summary.status,
                created_at=job_summary.created_at,
                updated_at=job_summary.updated_at,
                progress=job_summary.progress
            )
            job_responses.append(job_response)
        
        return JobListResponse(
            jobs=job_responses,
            total=result['total'],
            page=result['page'],
            page_size=result['page_size']
        )
        
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )