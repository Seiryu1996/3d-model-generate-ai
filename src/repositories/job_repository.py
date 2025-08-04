"""
Job repository implementation using document store.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from functools import lru_cache

import structlog

from .base import JobRepositoryInterface
from ..models.base import JobStatus
from ..models.job import Job, JobSummary
from ..utils.storage_adapter import get_storage_manager
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class JobRepository(JobRepositoryInterface):
    """Job repository implementation."""
    
    def __init__(self):
        self.settings = get_settings()
        self.storage_manager = get_storage_manager()
        self.collection = self.settings.FIRESTORE_COLLECTION_JOBS
    
    def _job_to_dict(self, job: Job) -> Dict[str, Any]:
        """Convert Job model to dictionary for storage."""
        data = job.dict()
        
        # Convert datetime objects to ISO strings for storage
        for field in ['created_at', 'updated_at', 'expires_at', 'started_at', 'completed_at']:
            if data.get(field):
                data[field] = data[field].isoformat()
        
        return data
    
    def _dict_to_job(self, data: Dict[str, Any]) -> Job:
        """Convert dictionary from storage to Job model."""
        # Convert ISO strings back to datetime objects
        for field in ['created_at', 'updated_at', 'expires_at', 'started_at', 'completed_at']:
            if data.get(field) and isinstance(data[field], str):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except ValueError:
                    logger.warning(f"Failed to parse datetime field {field}", value=data[field])
                    data[field] = None
        
        return Job(**data)
    
    async def create(self, job: Job) -> Job:
        """Create a new job."""
        try:
            data = self._job_to_dict(job)
            await self.storage_manager.document_store.create_document(
                self.collection, job.job_id, data
            )
            
            logger.info(
                "Job created in repository",
                job_id=job.job_id,
                user_id=job.user_id,
                job_type=job.job_type
            )
            
            return job
        except Exception as e:
            logger.error(
                "Failed to create job in repository",
                job_id=job.job_id,
                error=str(e)
            )
            raise
    
    async def get_by_id(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        try:
            data = await self.storage_manager.document_store.get_document(
                self.collection, job_id
            )
            
            if data:
                job = self._dict_to_job(data)
                logger.info("Job retrieved from repository", job_id=job_id)
                return job
            else:
                logger.info("Job not found in repository", job_id=job_id)
                return None
        except Exception as e:
            logger.error(
                "Failed to get job from repository",
                job_id=job_id,
                error=str(e)
            )
            raise
    
    async def update(self, job: Job) -> Job:
        """Update an existing job."""
        try:
            job.updated_at = datetime.utcnow()
            data = self._job_to_dict(job)
            
            await self.storage_manager.document_store.update_document(
                self.collection, job.job_id, data
            )
            
            logger.info(
                "Job updated in repository",
                job_id=job.job_id,
                status=job.status
            )
            
            return job
        except Exception as e:
            logger.error(
                "Failed to update job in repository",
                job_id=job.job_id,
                error=str(e)
            )
            raise
    
    async def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        try:
            await self.storage_manager.document_store.delete_document(
                self.collection, job_id
            )
            
            logger.info("Job deleted from repository", job_id=job_id)
            return True
        except Exception as e:
            logger.error(
                "Failed to delete job from repository",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def list(self, limit: int = 10, offset: int = 0, **filters) -> List[Job]:
        """List jobs with pagination and filtering."""
        # Note: This is a simplified implementation
        # In production, you would implement proper querying with filters
        logger.warning("JobRepository.list() not fully implemented - returning empty list")
        return []
    
    async def count(self, **filters) -> int:
        """Count jobs with filtering."""
        # Note: This is a simplified implementation
        logger.warning("JobRepository.count() not fully implemented - returning 0")
        return 0
    
    async def get_by_user_id(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Job]:
        """Get jobs by user ID."""
        # Note: This would require implementing query capabilities in the document store
        # For now, this is a placeholder implementation
        logger.warning("JobRepository.get_by_user_id() not fully implemented - returning empty list")
        return []
    
    async def get_by_status(self, status: JobStatus, limit: int = 10, offset: int = 0) -> List[Job]:
        """Get jobs by status."""
        # Note: This would require implementing query capabilities in the document store
        logger.warning("JobRepository.get_by_status() not fully implemented - returning empty list")
        return []
    
    async def get_pending_jobs(self, limit: int = 10) -> List[Job]:
        """Get jobs that are pending processing."""
        return await self.get_by_status(JobStatus.PENDING, limit=limit)
    
    async def get_expired_jobs(self, before_date: datetime) -> List[Job]:
        """Get jobs that have expired."""
        # Note: This would require implementing date-based queries
        logger.warning("JobRepository.get_expired_jobs() not fully implemented - returning empty list")
        return []
    
    async def update_status(self, job_id: str, status: JobStatus, **kwargs) -> bool:
        """Update job status and related fields."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                logger.warning("Job not found for status update", job_id=job_id)
                return False
            
            job.status = status
            
            # Update additional fields based on status
            if status == JobStatus.PROCESSING:
                job.started_at = kwargs.get('started_at', datetime.utcnow())
                job.worker_id = kwargs.get('worker_id')
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                job.completed_at = kwargs.get('completed_at', datetime.utcnow())
                if job.started_at:
                    job.processing_time_seconds = (
                        job.completed_at - job.started_at
                    ).total_seconds()
            
            if status == JobStatus.FAILED:
                job.error_message = kwargs.get('error_message')
            elif status == JobStatus.COMPLETED:
                job.output_files = kwargs.get('output_files', [])
                job.progress = 1.0
            
            await self.update(job)
            
            logger.info(
                "Job status updated",
                job_id=job_id,
                old_status=job.status,
                new_status=status
            )
            
            return True
        except Exception as e:
            logger.error(
                "Failed to update job status",
                job_id=job_id,
                status=status,
                error=str(e)
            )
            return False
    
    async def update_progress(self, job_id: str, progress: float) -> bool:
        """Update job progress."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                logger.warning("Job not found for progress update", job_id=job_id)
                return False
            
            job.update_progress(progress)
            await self.update(job)
            
            logger.info(
                "Job progress updated",
                job_id=job_id,
                progress=progress
            )
            
            return True
        except Exception as e:
            logger.error(
                "Failed to update job progress",
                job_id=job_id,
                progress=progress,
                error=str(e)
            )
            return False
    
    async def get_user_job_summaries(self, user_id: str, limit: int = 10, offset: int = 0) -> List[JobSummary]:
        """Get job summaries for a user."""
        try:
            jobs = await self.get_by_user_id(user_id, limit, offset)
            summaries = [
                JobSummary(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    progress=job.progress
                )
                for job in jobs
            ]
            
            logger.info(
                "Job summaries retrieved",
                user_id=user_id,
                count=len(summaries)
            )
            
            return summaries
        except Exception as e:
            logger.error(
                "Failed to get job summaries",
                user_id=user_id,
                error=str(e)
            )
            return []
    
    async def cleanup_expired_jobs(self, before_date: datetime) -> int:
        """Clean up expired jobs and return count of cleaned jobs."""
        try:
            expired_jobs = await self.get_expired_jobs(before_date)
            count = 0
            
            for job in expired_jobs:
                if await self.delete(job.job_id):
                    count += 1
            
            logger.info(
                "Expired jobs cleaned up",
                count=count,
                before_date=before_date
            )
            
            return count
        except Exception as e:
            logger.error(
                "Failed to cleanup expired jobs",
                before_date=before_date,
                error=str(e)
            )
            return 0


@lru_cache()
def get_job_repository() -> JobRepository:
    """Get cached job repository instance."""
    return JobRepository()