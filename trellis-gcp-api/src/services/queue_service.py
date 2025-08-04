"""
Queue management service for handling job processing.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from functools import lru_cache

import structlog

from ..models.base import JobStatus, JobType
from ..models.job import Job
from ..utils.storage_adapter import get_storage_manager
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class QueueServiceError(Exception):
    """Base exception for queue service errors."""
    pass


class QueueService:
    """Service for managing job queues and task processing."""
    
    def __init__(self):
        self.settings = get_settings()
        self.storage_manager = get_storage_manager()
        self.queue_name = self.settings.CLOUD_TASKS_QUEUE
    
    async def submit_job(self, job: Job, delay_seconds: int = 0) -> str:
        """Submit a job to the processing queue."""
        try:
            # Prepare job payload
            payload = {
                'job_id': job.job_id,
                'user_id': job.user_id,
                'job_type': job.job_type.value,
                'input_data': job.input_data,
                'created_at': job.created_at.isoformat(),
                'quality': job.input_data.get('quality', 'balanced'),
                'output_formats': job.input_data.get('output_formats', ['glb'])
            }
            
            # Submit to task queue
            task_id = await self.storage_manager.task_queue.create_task(
                self.queue_name,
                payload,
                delay_seconds
            )
            
            logger.info(
                "Job submitted to queue",
                job_id=job.job_id,
                task_id=task_id,
                queue=self.queue_name,
                job_type=job.job_type,
                delay_seconds=delay_seconds
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to submit job to queue",
                job_id=job.job_id,
                queue=self.queue_name,
                error=str(e)
            )
            raise QueueServiceError(f"Failed to submit job to queue: {e}")
    
    async def submit_retry_job(self, job: Job, retry_delay_minutes: int = 5) -> str:
        """Submit a failed job for retry with exponential backoff."""
        try:
            # Calculate retry delay with exponential backoff
            delay_seconds = retry_delay_minutes * 60 * (2 ** job.retry_count)
            max_delay = 30 * 60  # Maximum 30 minutes
            delay_seconds = min(delay_seconds, max_delay)
            
            # Increment retry count
            job.retry_count += 1
            
            task_id = await self.submit_job(job, delay_seconds)
            
            logger.info(
                "Job submitted for retry",
                job_id=job.job_id,
                retry_count=job.retry_count,
                delay_seconds=delay_seconds,
                task_id=task_id
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to submit job for retry",
                job_id=job.job_id,
                retry_count=job.retry_count,
                error=str(e)
            )
            raise QueueServiceError(f"Failed to submit retry job: {e}")
    
    async def cancel_job_in_queue(self, job_id: str) -> bool:
        """Cancel a job in the queue (if supported by the queue implementation)."""
        try:
            # Note: This is a placeholder implementation
            # In a real implementation, you would need to:
            # 1. Find the task in the queue by job_id
            # 2. Delete/cancel the task
            # 3. Update job status to cancelled
            
            logger.info(
                "Job cancellation requested",
                job_id=job_id,
                queue=self.queue_name
            )
            
            # For local development, this would be implemented in the local task queue
            # For GCP Cloud Tasks, you would need to track task names and use the tasks client
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to cancel job in queue",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        try:
            # This would be implemented differently for different queue backends
            stats = {
                'queue_name': self.queue_name,
                'pending_tasks': 0,  # Would be fetched from actual queue
                'processing_tasks': 0,
                'failed_tasks': 0,
                'total_processed': 0,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            logger.info(
                "Queue stats retrieved",
                queue=self.queue_name,
                stats=stats
            )
            
            return stats
            
        except Exception as e:
            logger.error(
                "Failed to get queue stats",
                queue=self.queue_name,
                error=str(e)
            )
            return {}
    
    async def create_image_processing_task(self, job: Job, image_data: bytes = None, image_url: str = None) -> str:
        """Create a specialized task for image-to-3D processing."""
        try:
            # Prepare image processing payload
            payload = {
                'job_id': job.job_id,
                'job_type': 'image-to-3d',
                'processing_type': 'trellis_image_pipeline',
                'input_data': job.input_data,
                'has_image_data': image_data is not None,
                'image_url': image_url,
                'quality': job.input_data.get('quality', 'balanced'),
                'output_formats': job.input_data.get('output_formats', ['glb']),
                'created_at': job.created_at.isoformat()
            }
            
            # If we have image data, we'd typically upload it to storage first
            if image_data:
                # Upload image to input bucket
                bucket_names = self.storage_manager.get_bucket_names()
                image_filename = f"{job.job_id}_input.jpg"
                image_url = await self.storage_manager.storage.upload_from_bytes(
                    bucket_names['input'],
                    image_data,
                    image_filename,
                    'image/jpeg'
                )
                payload['image_url'] = image_url
            
            task_id = await self.storage_manager.task_queue.create_task(
                self.queue_name,
                payload
            )
            
            logger.info(
                "Image processing task created",
                job_id=job.job_id,
                task_id=task_id,
                has_image_data=image_data is not None,
                image_url=image_url
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to create image processing task",
                job_id=job.job_id,
                error=str(e)
            )
            raise QueueServiceError(f"Failed to create image processing task: {e}")
    
    async def create_text_processing_task(self, job: Job) -> str:
        """Create a specialized task for text-to-3D processing."""
        try:
            # Prepare text processing payload
            payload = {
                'job_id': job.job_id,
                'job_type': 'text-to-3d',
                'processing_type': 'trellis_text_pipeline',
                'input_data': job.input_data,
                'prompt': job.input_data.get('prompt', ''),
                'negative_prompt': job.input_data.get('negative_prompt', ''),
                'quality': job.input_data.get('quality', 'balanced'),
                'output_formats': job.input_data.get('output_formats', ['glb']),
                'created_at': job.created_at.isoformat()
            }
            
            task_id = await self.storage_manager.task_queue.create_task(
                self.queue_name,
                payload
            )
            
            logger.info(
                "Text processing task created",
                job_id=job.job_id,
                task_id=task_id,
                prompt_length=len(job.input_data.get('prompt', ''))
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to create text processing task",
                job_id=job.job_id,
                error=str(e)
            )
            raise QueueServiceError(f"Failed to create text processing task: {e}")
    
    async def process_task_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task webhook from the queue system."""
        try:
            job_id = payload.get('job_id')
            if not job_id:
                raise QueueServiceError("Missing job_id in task payload")
            
            logger.info(
                "Processing task webhook",
                job_id=job_id,
                job_type=payload.get('job_type'),
                processing_type=payload.get('processing_type')
            )
            
            # Import worker service for processing
            from .worker_service import get_worker_service
            
            worker_service = get_worker_service()
            
            # Process the job asynchronously
            result = await worker_service.process_job_from_payload(payload)
            
            response = {
                'status': result.get('status', 'processed'),
                'job_id': job_id,
                'processed_at': datetime.utcnow().isoformat(),
                'message': 'Task processed successfully',
                'result': result
            }
            
            return response
            
        except Exception as e:
            logger.error(
                "Failed to process task webhook",
                payload=payload,
                error=str(e)
            )
            raise QueueServiceError(f"Failed to process task webhook: {e}")
    
    async def handle_task_failure(self, job_id: str, error_message: str, retry: bool = True) -> bool:
        """Handle task failure and optionally retry."""
        try:
            from ..repositories.job_repository import get_job_repository
            from ..services.job_service import get_job_service
            
            job_repository = get_job_repository()
            job_service = get_job_service()
            
            # Get the job
            job = await job_repository.get_by_id(job_id)
            if not job:
                logger.error("Job not found for failure handling", job_id=job_id)
                return False
            
            # Check if we should retry
            max_retries = 3
            if retry and job.retry_count < max_retries:
                # Mark as pending for retry
                await job_repository.update_status(job_id, JobStatus.PENDING)
                
                # Submit for retry
                await self.submit_retry_job(job)
                
                logger.info(
                    "Job scheduled for retry",
                    job_id=job_id,
                    retry_count=job.retry_count,
                    error_message=error_message
                )
                
                return True
            else:
                # Mark as permanently failed
                await job_service.mark_job_failed(job_id, error_message)
                
                logger.info(
                    "Job marked as permanently failed",
                    job_id=job_id,
                    retry_count=job.retry_count,
                    error_message=error_message
                )
                
                return False
                
        except Exception as e:
            logger.error(
                "Failed to handle task failure",
                job_id=job_id,
                error_message=error_message,
                error=str(e)
            )
            return False


@lru_cache()
def get_queue_service() -> QueueService:
    """Get cached queue service instance."""
    return QueueService()