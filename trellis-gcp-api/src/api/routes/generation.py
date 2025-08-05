"""
3D model generation endpoints.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends
import structlog

from ...models.api import ImageTo3DRequest, TextTo3DRequest, JobResponse
from ...models.job import Job, JobType, ImageTo3DInput, TextTo3DInput
from ...services.job_service import get_job_service, JobServiceError
from ...utils.config import get_settings
from ...utils.auth import get_current_user_id, rate_limit_check

router = APIRouter()
logger = structlog.get_logger(__name__)




@router.post(
    "/generate/image-to-3d",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate 3D Model from Image",
    description="Create a job to generate a 3D model from an input image."
)
async def generate_3d_from_image(
    request: ImageTo3DRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit_check)
) -> JobResponse:
    """Generate 3D model from image."""
    job_service = get_job_service()
    
    logger.info(
        "Received image-to-3D request",
        user_id=user_id,
        has_image_url=bool(request.image_url),
        has_image_base64=bool(request.image_base64),
        output_formats=request.output_formats,
        quality=request.quality
    )
    
    # Validate input
    if not request.image_url and not request.image_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either image_url or image_base64 must be provided"
        )
    
    try:
        # Create input data
        input_data = ImageTo3DInput(
            image_url=str(request.image_url) if request.image_url else None,
            image_base64=request.image_base64,
            output_formats=request.output_formats,
            quality=request.quality
        )
        
        # Create job through service
        job = await job_service.create_image_to_3d_job(user_id, input_data)
        
        # Estimate completion time (placeholder)
        estimated_completion = datetime.utcnow() + timedelta(
            minutes=5 if request.quality == "fast" else 15 if request.quality == "balanced" else 30
        )
        
        return JobResponse(
            job_id=job.job_id,
            status=job.status,
            estimated_completion_time=estimated_completion
        )
    
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create 3D generation job"
        )
    except Exception as e:
        logger.error("Unexpected error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/generate/text-to-3d",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate 3D Model from Text",
    description="Create a job to generate a 3D model from a text prompt."
)
async def generate_3d_from_text(
    request: TextTo3DRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit_check)
) -> JobResponse:
    """Generate 3D model from text prompt."""
    job_service = get_job_service()
    
    logger.info(
        "Received text-to-3D request",
        user_id=user_id,
        prompt_length=len(request.prompt),
        output_formats=request.output_formats,
        quality=request.quality
    )
    
    try:
        # Create input data
        input_data = TextTo3DInput(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            output_formats=request.output_formats,
            quality=request.quality
        )
        
        # Create job through service
        job = await job_service.create_text_to_3d_job(user_id, input_data)
        
        # Estimate completion time (placeholder)
        estimated_completion = datetime.utcnow() + timedelta(
            minutes=10 if request.quality == "fast" else 20 if request.quality == "balanced" else 45
        )
        
        return JobResponse(
            job_id=job.job_id,
            status=job.status,
            estimated_completion_time=estimated_completion
        )
    
    except JobServiceError as e:
        logger.error("Job service error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create 3D generation job"
        )
    except Exception as e:
        logger.error("Unexpected error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )