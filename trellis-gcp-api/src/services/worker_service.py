"""
Worker service for processing TRELLIS jobs from the queue.

This service handles the actual processing of queued jobs using the TRELLIS service
and manages job lifecycle, progress reporting, and error handling.
"""
import asyncio
import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime

import structlog

from ..models.base import JobStatus, JobType
from ..models.job import Job
from ..services.trellis_service import get_trellis_service, TrellisServiceError
from ..services.job_service import get_job_service
from ..services.queue_service import get_queue_service
from ..repositories.job_repository import get_job_repository
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class WorkerServiceError(Exception):
    """Base exception for worker service errors."""
    pass


class WorkerService:
    """Service for processing TRELLIS jobs from the queue."""
    
    def __init__(self):
        self.settings = get_settings()
        self.trellis_service = get_trellis_service()
        self.job_service = get_job_service()
        self.queue_service = get_queue_service()
        self.job_repository = get_job_repository()
        self._processing_jobs = set()
    
    async def process_job_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a job from queue payload.
        
        Args:
            payload: Job payload from the queue
            
        Returns:
            Processing result
        """
        job_id = payload.get('job_id')
        
        try:
            if not job_id:
                raise WorkerServiceError("Missing job_id in payload")
            
            # Check if already processing
            if job_id in self._processing_jobs:
                logger.warning("Job already being processed", job_id=job_id)
                return {'status': 'already_processing', 'job_id': job_id}
            
            # Add to processing set
            self._processing_jobs.add(job_id)
            
            logger.info(
                "Starting job processing",
                job_id=job_id,
                job_type=payload.get('job_type'),
                processing_type=payload.get('processing_type')
            )
            
            # Get job from repository
            job = await self.job_repository.get_by_id(job_id)
            if not job:
                raise WorkerServiceError(f"Job {job_id} not found")
            
            # Update job status to processing
            await self.job_repository.update_status(job_id, JobStatus.PROCESSING)
            
            # Process based on job type
            if job.job_type == JobType.IMAGE_TO_3D:
                result = await self._process_image_to_3d_job(job, payload)
            elif job.job_type == JobType.TEXT_TO_3D:
                result = await self._process_text_to_3d_job(job, payload)
            else:
                raise WorkerServiceError(f"Unsupported job type: {job.job_type}")
            
            logger.info(
                "Job processing completed successfully",
                job_id=job_id,
                output_files_count=len(result.get('output_files', []))
            )
            
            return {
                'status': 'completed',
                'job_id': job_id,
                'result': result,
                'processed_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(
                "Job processing failed",
                job_id=job_id,
                error=str(e)
            )
            
            # Handle failure
            if job_id:
                try:
                    await self._handle_job_failure(job_id, str(e))
                except Exception as cleanup_error:
                    logger.error(
                        "Failed to handle job failure",
                        job_id=job_id,
                        cleanup_error=str(cleanup_error)
                    )
            
            return {
                'status': 'failed',
                'job_id': job_id,
                'error': str(e),
                'failed_at': datetime.utcnow().isoformat()
            }
            
        finally:
            # Remove from processing set
            if job_id:
                self._processing_jobs.discard(job_id)
    
    async def _process_image_to_3d_job(self, job: Job, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process an image-to-3D job."""
        try:
            logger.info("Processing image-to-3D job", job_id=job.job_id)
            
            # Create progress callback
            async def progress_callback(progress: float, message: str = ""):
                await self._update_job_progress(job.job_id, progress, message)
            
            # Get image data from payload or storage
            image_data = None
            image_url = payload.get('image_url')
            
            if payload.get('has_image_data'):
                # Image data should be available in storage
                # This would be implemented based on the storage strategy
                pass
            
            # Process with TRELLIS
            output_files = await self.trellis_service.process_image_to_3d(
                job=job,
                image_data=image_data,
                image_url=image_url,
                progress_callback=progress_callback
            )
            
            # Mark job as completed
            await self.job_service.mark_job_completed(job.job_id, output_files)
            
            return {
                'job_id': job.job_id,
                'status': 'completed',
                'output_files': [file.dict() for file in output_files],
                'processing_time_seconds': (datetime.utcnow() - job.created_at).total_seconds()
            }
            
        except TrellisServiceError as e:
            logger.error(
                "TRELLIS processing failed for image-to-3D job",
                job_id=job.job_id,
                error=str(e)
            )
            raise WorkerServiceError(f"Image-to-3D processing failed: {e}")
        except Exception as e:
            logger.error(
                "Unexpected error during image-to-3D processing",
                job_id=job.job_id,
                error=str(e)
            )
            raise WorkerServiceError(f"Image-to-3D job processing failed: {e}")
    
    async def _process_text_to_3d_job(self, job: Job, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a text-to-3D job."""
        try:
            logger.info("Processing text-to-3D job", job_id=job.job_id)
            
            # Create progress callback
            async def progress_callback(progress: float, message: str = ""):
                await self._update_job_progress(job.job_id, progress, message)
            
            # Process with TRELLIS
            output_files = await self.trellis_service.process_text_to_3d(
                job=job,
                progress_callback=progress_callback
            )
            
            # Mark job as completed
            await self.job_service.mark_job_completed(job.job_id, output_files)
            
            return {
                'job_id': job.job_id,
                'status': 'completed',
                'output_files': [file.dict() for file in output_files],
                'processing_time_seconds': (datetime.utcnow() - job.created_at).total_seconds()
            }
            
        except TrellisServiceError as e:
            logger.error(
                "TRELLIS processing failed for text-to-3D job",
                job_id=job.job_id,
                error=str(e)
            )
            raise WorkerServiceError(f"Text-to-3D processing failed: {e}")
        except Exception as e:
            logger.error(
                "Unexpected error during text-to-3D processing",
                job_id=job.job_id,
                error=str(e)
            )
            raise WorkerServiceError(f"Text-to-3D job processing failed: {e}")
    
    async def _update_job_progress(
        self,
        job_id: str,
        progress: float,
        message: str = ""
    ) -> None:
        """Update job progress."""
        try:
            success = await self.job_service.update_job_progress(job_id, progress)
            
            if success:
                logger.info(
                    "Job progress updated",
                    job_id=job_id,
                    progress=progress,
                    message=message
                )
            else:
                logger.warning(
                    "Failed to update job progress",
                    job_id=job_id,
                    progress=progress
                )
                
        except Exception as e:
            logger.error(
                "Error updating job progress",
                job_id=job_id,
                progress=progress,
                error=str(e)
            )
    
    async def _handle_job_failure(self, job_id: str, error_message: str) -> None:
        """Handle job failure."""
        try:
            # Use queue service to handle failure with retry logic
            await self.queue_service.handle_task_failure(job_id, error_message, retry=True)
            
            logger.info(
                "Job failure handled",
                job_id=job_id,
                error_message=error_message
            )
            
        except Exception as e:
            logger.error(
                "Failed to handle job failure",
                job_id=job_id,
                error_message=error_message,
                error=str(e)
            )
    
    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processing status."""
        model_info = self.trellis_service.get_model_info()
        
        return {
            'currently_processing': list(self._processing_jobs),
            'processing_count': len(self._processing_jobs),
            'model_info': model_info,
            'worker_status': 'ready',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        try:
            # Check model loading capability
            model_info = self.trellis_service.get_model_info()
            
            # Check storage connectivity
            storage_healthy = True
            try:
                bucket_names = self.trellis_service.storage_manager.get_bucket_names()
                # Basic storage check could be performed here
            except Exception as e:
                storage_healthy = False
                logger.warning("Storage health check failed", error=str(e))
            
            return {
                'status': 'healthy',
                'model_info': model_info,
                'storage_healthy': storage_healthy,
                'processing_jobs': len(self._processing_jobs),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Worker health check failed", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }


# Global worker service instance
_worker_service = None


def get_worker_service() -> WorkerService:
    """Get worker service instance."""
    global _worker_service
    if _worker_service is None:
        _worker_service = WorkerService()
    return _worker_service