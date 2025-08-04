"""
Job management service layer.
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from functools import lru_cache

import structlog

from ..models.base import JobStatus, JobType
from ..models.job import Job, JobSummary, ImageTo3DInput, TextTo3DInput, JobOutputFile
from ..repositories.job_repository import get_job_repository
from ..utils.storage_adapter import get_storage_manager
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class JobServiceError(Exception):
    """Base exception for job service errors."""
    pass


class JobNotFoundError(JobServiceError):
    """Exception raised when a job is not found."""
    pass


class JobAccessDeniedError(JobServiceError):
    """Exception raised when user doesn't have access to a job."""
    pass


class JobService:
    """Service for managing 3D generation jobs."""
    
    def __init__(self):
        self.settings = get_settings()
        self.job_repository = get_job_repository()
        self.storage_manager = get_storage_manager()
    
    async def create_image_to_3d_job(self, user_id: str, input_data: ImageTo3DInput) -> Job:
        """Create a new image-to-3D job."""
        try:
            job = Job(
                user_id=user_id,
                job_type=JobType.IMAGE_TO_3D,
                input_data=input_data.dict()
            )
            
            created_job = await self.job_repository.create(job)
            
            # Submit job to processing queue
            await self._submit_job_to_queue(created_job)
            
            logger.info(
                "Image-to-3D job created",
                job_id=created_job.job_id,
                user_id=user_id,
                quality=input_data.quality,
                output_formats=input_data.output_formats
            )
            
            return created_job
            
        except Exception as e:
            logger.error(
                "Failed to create image-to-3D job",
                user_id=user_id,
                error=str(e)
            )
            raise JobServiceError(f"Failed to create job: {e}")
    
    async def create_text_to_3d_job(self, user_id: str, input_data: TextTo3DInput) -> Job:
        """Create a new text-to-3D job."""
        try:
            job = Job(
                user_id=user_id,
                job_type=JobType.TEXT_TO_3D,
                input_data=input_data.dict()
            )
            
            created_job = await self.job_repository.create(job)
            
            # Submit job to processing queue
            await self._submit_job_to_queue(created_job)
            
            logger.info(
                "Text-to-3D job created",
                job_id=created_job.job_id,
                user_id=user_id,
                prompt=input_data.prompt[:50] + "..." if len(input_data.prompt) > 50 else input_data.prompt,
                quality=input_data.quality,
                output_formats=input_data.output_formats
            )
            
            return created_job
            
        except Exception as e:
            logger.error(
                "Failed to create text-to-3D job",
                user_id=user_id,
                error=str(e)
            )
            raise JobServiceError(f"Failed to create job: {e}")
    
    async def get_job(self, job_id: str, user_id: str) -> Job:
        """Get a job by ID, ensuring user has access."""
        job = await self.job_repository.get_by_id(job_id)
        
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found")
        
        if job.user_id != user_id:
            raise JobAccessDeniedError(f"User {user_id} does not have access to job {job_id}")
        
        return job
    
    async def get_job_status(self, job_id: str, user_id: str) -> Job:
        """Get job status."""
        return await self.get_job(job_id, user_id)
    
    async def get_job_result(self, job_id: str, user_id: str) -> Job:
        """Get job result."""
        job = await self.get_job(job_id, user_id)
        
        if not job.is_finished():
            logger.info(
                "Job result requested but job not finished",
                job_id=job_id,
                status=job.status
            )
        
        return job
    
    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        """Cancel a job."""
        job = await self.get_job(job_id, user_id)
        
        if not job.can_be_cancelled():
            logger.warning(
                "Cannot cancel job in current status",
                job_id=job_id,
                status=job.status
            )
            return False
        
        try:
            from .queue_service import get_queue_service
            
            # Cancel in queue first
            queue_service = get_queue_service()
            queue_cancelled = await queue_service.cancel_job_in_queue(job_id)
            
            # Mark job as cancelled
            job.mark_as_cancelled()
            await self.job_repository.update(job)
            
            logger.info(
                "Job cancelled", 
                job_id=job_id, 
                user_id=user_id,
                queue_cancelled=queue_cancelled
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to cancel job",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def delete_job(self, job_id: str, user_id: str) -> bool:
        """Delete a job and clean up its resources."""
        job = await self.get_job(job_id, user_id)
        
        try:
            # Cancel job if it's still processing
            if job.can_be_cancelled():
                await self.cancel_job(job_id, user_id)
            
            # Clean up output files
            await self._cleanup_job_files(job)
            
            # Delete job from repository
            success = await self.job_repository.delete(job_id)
            
            if success:
                logger.info("Job deleted", job_id=job_id, user_id=user_id)
            else:
                logger.error("Failed to delete job from repository", job_id=job_id)
            
            return success
            
        except Exception as e:
            logger.error(
                "Failed to delete job",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def list_user_jobs(self, user_id: str, page: int = 1, page_size: int = 10, status_filter: Optional[JobStatus] = None) -> Dict[str, Any]:
        """List jobs for a user with pagination."""
        try:
            offset = (page - 1) * page_size
            
            if status_filter:
                # Get jobs by status for the user
                # Note: This would need proper implementation in the repository
                jobs = []
            else:
                # Get all jobs for the user
                jobs = await self.job_repository.get_by_user_id(user_id, page_size, offset)
            
            # Get job summaries
            summaries = await self.job_repository.get_user_job_summaries(user_id, page_size, offset)
            
            # Get total count (placeholder implementation)
            total = len(summaries)  # This should be replaced with proper count query
            
            logger.info(
                "User jobs listed",
                user_id=user_id,
                page=page,
                page_size=page_size,
                total=total,
                status_filter=status_filter
            )
            
            return {
                'jobs': summaries,
                'total': total,
                'page': page,
                'page_size': page_size
            }
            
        except Exception as e:
            logger.error(
                "Failed to list user jobs",
                user_id=user_id,
                error=str(e)
            )
            raise JobServiceError(f"Failed to list jobs: {e}")
    
    async def update_job_progress(self, job_id: str, progress: float, worker_id: str = None) -> bool:
        """Update job progress (called by worker)."""
        try:
            success = await self.job_repository.update_progress(job_id, progress)
            
            if success:
                logger.info(
                    "Job progress updated",
                    job_id=job_id,
                    progress=progress,
                    worker_id=worker_id
                )
            
            return success
            
        except Exception as e:
            logger.error(
                "Failed to update job progress",
                job_id=job_id,
                progress=progress,
                error=str(e)
            )
            return False
    
    async def mark_job_completed(self, job_id: str, output_files: List[JobOutputFile], worker_id: str = None) -> bool:
        """Mark a job as completed (called by worker)."""
        try:
            success = await self.job_repository.update_status(
                job_id,
                JobStatus.COMPLETED,
                output_files=output_files,
                completed_at=datetime.utcnow()
            )
            
            if success:
                logger.info(
                    "Job marked as completed",
                    job_id=job_id,
                    output_files_count=len(output_files),
                    worker_id=worker_id
                )
            
            return success
            
        except Exception as e:
            logger.error(
                "Failed to mark job as completed",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def mark_job_failed(self, job_id: str, error_message: str, worker_id: str = None) -> bool:
        """Mark a job as failed (called by worker)."""
        try:
            success = await self.job_repository.update_status(
                job_id,
                JobStatus.FAILED,
                error_message=error_message,
                completed_at=datetime.utcnow()
            )
            
            if success:
                logger.info(
                    "Job marked as failed",
                    job_id=job_id,
                    error_message=error_message,
                    worker_id=worker_id
                )
            
            return success
            
        except Exception as e:
            logger.error(
                "Failed to mark job as failed",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def cleanup_expired_jobs(self) -> int:
        """Clean up expired jobs."""
        try:
            expiry_date = datetime.utcnow() - timedelta(days=self.settings.OUTPUT_EXPIRY_DAYS)
            count = await self.job_repository.cleanup_expired_jobs(expiry_date)
            
            logger.info(
                "Expired jobs cleanup completed",
                count=count,
                expiry_date=expiry_date
            )
            
            return count
            
        except Exception as e:
            logger.error(
                "Failed to cleanup expired jobs",
                error=str(e)
            )
            return 0
    
    async def _submit_job_to_queue(self, job: Job) -> None:
        """Submit a job to the processing queue."""
        try:
            from .queue_service import get_queue_service
            
            queue_service = get_queue_service()
            
            # Submit job based on type
            if job.job_type == JobType.IMAGE_TO_3D:
                task_id = await queue_service.create_image_processing_task(job)
            elif job.job_type == JobType.TEXT_TO_3D:
                task_id = await queue_service.create_text_processing_task(job)
            else:
                # Fallback to generic submission
                task_id = await queue_service.submit_job(job)
            
            logger.info(
                "Job submitted to specialized queue",
                job_id=job.job_id,
                task_id=task_id,
                job_type=job.job_type
            )
            
        except Exception as e:
            logger.error(
                "Failed to submit job to queue",
                job_id=job.job_id,
                error=str(e)
            )
            # Don't raise here - job is already created
    
    async def _cleanup_job_files(self, job: Job) -> None:
        """Clean up files associated with a job."""
        try:
            bucket_names = self.storage_manager.get_bucket_names()
            
            # Clean up output files
            for output_file in job.output_files:
                try:
                    if output_file.url.startswith('gs://') or output_file.url.startswith('minio://'):
                        # Extract bucket and file name from URL
                        url_parts = output_file.url.replace('gs://', '').replace('minio://', '').split('/', 1)
                        if len(url_parts) == 2:
                            bucket_name, file_name = url_parts
                            await self.storage_manager.storage.delete_file(bucket_name, file_name)
                            
                            logger.info(
                                "Job output file deleted",
                                job_id=job.job_id,
                                file_url=output_file.url
                            )
                except Exception as e:
                    logger.warning(
                        "Failed to delete job output file",
                        job_id=job.job_id,
                        file_url=output_file.url,
                        error=str(e)
                    )
            
            # Clean up temporary files
            try:
                temp_bucket = bucket_names['temp']
                # This would require listing files with job_id prefix
                # For now, just log the intent
                logger.info(
                    "Cleaning up temporary files for job",
                    job_id=job.job_id,
                    temp_bucket=temp_bucket
                )
            except Exception as e:
                logger.warning(
                    "Failed to cleanup temporary files",
                    job_id=job.job_id,
                    error=str(e)
                )
                
        except Exception as e:
            logger.error(
                "Failed to cleanup job files",
                job_id=job.job_id,
                error=str(e)
            )


@lru_cache()
def get_job_service() -> JobService:
    """Get cached job service instance."""
    return JobService()