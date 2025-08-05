"""
Job repository for data persistence operations.

This module provides data access methods for job management using the repository pattern.
It supports both Firestore (production) and in-memory storage (development).
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from functools import lru_cache
import asyncio

import structlog

from ..models.base import JobStatus, JobType
from ..models.job import Job, JobSummary, JobOutputFile
from ..utils.config import get_settings


logger = structlog.get_logger(__name__)


class JobRepositoryError(Exception):
    """Base exception for job repository errors."""
    pass


class JobRepository:
    """Repository for job data operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self._jobs_cache: Dict[str, Job] = {}  # In-memory cache for development
    
    async def create(self, job: Job) -> Job:
        """Create a new job."""
        try:
            if not job.job_id:
                job.job_id = str(uuid.uuid4())
            
            if not job.created_at:
                job.created_at = datetime.utcnow()
            
            job.updated_at = datetime.utcnow()
            
            if self.settings.is_development():
                # Use in-memory storage for development
                self._jobs_cache[job.job_id] = job
                
                logger.info(
                    "Job created in memory",
                    job_id=job.job_id,
                    job_type=job.job_type,
                    user_id=job.user_id
                )
            else:
                # Use Firestore for production
                await self._create_in_firestore(job)
                
                logger.info(
                    "Job created in Firestore",
                    job_id=job.job_id,
                    job_type=job.job_type,
                    user_id=job.user_id
                )
            
            return job
            
        except Exception as e:
            logger.error(
                "Failed to create job",
                job_id=getattr(job, 'job_id', None),
                error=str(e)
            )
            raise JobRepositoryError(f"Failed to create job: {e}")
    
    async def get_by_id(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        try:
            if self.settings.is_development():
                # Get from in-memory storage
                job = self._jobs_cache.get(job_id)
                
                if job:
                    logger.debug("Job retrieved from memory", job_id=job_id)
                else:
                    logger.debug("Job not found in memory", job_id=job_id)
                
                return job
            else:
                # Get from Firestore
                job = await self._get_from_firestore(job_id)
                
                if job:
                    logger.debug("Job retrieved from Firestore", job_id=job_id)
                else:
                    logger.debug("Job not found in Firestore", job_id=job_id)
                
                return job
                
        except Exception as e:
            logger.error(
                "Failed to get job by ID",
                job_id=job_id,
                error=str(e)
            )
            raise JobRepositoryError(f"Failed to get job: {e}")
    
    async def update(self, job: Job) -> Job:
        """Update an existing job."""
        try:
            job.updated_at = datetime.utcnow()
            
            if self.settings.is_development():
                # Update in-memory storage
                if job.job_id in self._jobs_cache:
                    self._jobs_cache[job.job_id] = job
                    
                    logger.info(
                        "Job updated in memory",
                        job_id=job.job_id,
                        status=job.status
                    )
                else:
                    raise JobRepositoryError(f"Job {job.job_id} not found for update")
            else:
                # Update in Firestore
                await self._update_in_firestore(job)
                
                logger.info(
                    "Job updated in Firestore",
                    job_id=job.job_id,
                    status=job.status
                )
            
            return job
            
        except Exception as e:
            logger.error(
                "Failed to update job",
                job_id=job.job_id,
                error=str(e)
            )
            raise JobRepositoryError(f"Failed to update job: {e}")
    
    async def delete(self, job_id: str) -> bool:
        """Delete a job."""
        try:
            if self.settings.is_development():
                # Delete from in-memory storage
                if job_id in self._jobs_cache:
                    del self._jobs_cache[job_id]
                    
                    logger.info("Job deleted from memory", job_id=job_id)
                    return True
                else:
                    logger.warning("Job not found for deletion", job_id=job_id)
                    return False
            else:
                # Delete from Firestore
                success = await self._delete_from_firestore(job_id)
                
                if success:
                    logger.info("Job deleted from Firestore", job_id=job_id)
                else:
                    logger.warning("Job not found for deletion in Firestore", job_id=job_id)
                
                return success
                
        except Exception as e:
            logger.error(
                "Failed to delete job",
                job_id=job_id,
                error=str(e)
            )
            return False
    
    async def get_by_user_id(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Job]:
        """Get jobs by user ID with pagination."""
        try:
            if self.settings.is_development():
                # Filter from in-memory storage
                user_jobs = [
                    job for job in self._jobs_cache.values()
                    if job.user_id == user_id
                ]
                
                # Sort by created_at desc
                user_jobs.sort(key=lambda x: x.created_at, reverse=True)
                
                # Apply pagination
                paginated_jobs = user_jobs[offset:offset + limit]
                
                logger.debug(
                    "Jobs retrieved by user ID from memory",
                    user_id=user_id,
                    total=len(user_jobs),
                    returned=len(paginated_jobs)
                )
                
                return paginated_jobs
            else:
                # Get from Firestore
                jobs = await self._get_by_user_from_firestore(user_id, limit, offset)
                
                logger.debug(
                    "Jobs retrieved by user ID from Firestore",
                    user_id=user_id,
                    returned=len(jobs)
                )
                
                return jobs
                
        except Exception as e:
            logger.error(
                "Failed to get jobs by user ID",
                user_id=user_id,
                error=str(e)
            )
            raise JobRepositoryError(f"Failed to get jobs by user: {e}")
    
    async def get_user_job_summaries(self, user_id: str, limit: int = 10, offset: int = 0) -> List[JobSummary]:
        """Get job summaries for a user."""
        try:
            jobs = await self.get_by_user_id(user_id, limit, offset)
            
            summaries = []
            for job in jobs:
                summary = JobSummary(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    progress=job.progress
                )
                summaries.append(summary)
            
            logger.debug(
                "Job summaries created",
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
            raise JobRepositoryError(f"Failed to get job summaries: {e}")
    
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: str = None,
        output_files: List[JobOutputFile] = None,
        completed_at: datetime = None
    ) -> bool:
        """Update job status and related fields."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                logger.warning("Job not found for status update", job_id=job_id)
                return False
            
            job.status = status
            job.updated_at = datetime.utcnow()
            
            if error_message:
                job.error_message = error_message
            
            if output_files:
                job.output_files = output_files
            
            if completed_at:
                job.completed_at = completed_at
            
            if status == JobStatus.PROCESSING and not job.started_at:
                job.started_at = datetime.utcnow()
            
            await self.update(job)
            
            logger.info(
                "Job status updated",
                job_id=job_id,
                status=status,
                error_message=error_message
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
            
            job.progress = progress
            job.updated_at = datetime.utcnow()
            
            await self.update(job)
            
            logger.debug(
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
    
    async def cleanup_expired_jobs(self, expiry_date: datetime) -> int:
        """Clean up jobs older than expiry date."""
        try:
            count = 0
            
            if self.settings.is_development():
                # Clean up from in-memory storage
                expired_jobs = [
                    job_id for job_id, job in self._jobs_cache.items()
                    if job.created_at < expiry_date
                ]
                
                for job_id in expired_jobs:
                    del self._jobs_cache[job_id]
                    count += 1
                
                logger.info(
                    "Expired jobs cleaned up from memory",
                    count=count,
                    expiry_date=expiry_date
                )
            else:
                # Clean up from Firestore
                count = await self._cleanup_expired_from_firestore(expiry_date)
                
                logger.info(
                    "Expired jobs cleaned up from Firestore",
                    count=count,
                    expiry_date=expiry_date
                )
            
            return count
            
        except Exception as e:
            logger.error(
                "Failed to cleanup expired jobs",
                expiry_date=expiry_date,
                error=str(e)
            )
            return 0
    
    # Firestore-specific methods (placeholders for production)
    async def _create_in_firestore(self, job: Job) -> None:
        """Create job in Firestore."""
        # TODO: Implement Firestore job creation
        # from google.cloud import firestore
        # db = firestore.Client()
        # doc_ref = db.collection('jobs').document(job.job_id)
        # await doc_ref.set(job.dict())
        pass
    
    async def _get_from_firestore(self, job_id: str) -> Optional[Job]:
        """Get job from Firestore."""
        # TODO: Implement Firestore job retrieval
        # from google.cloud import firestore
        # db = firestore.Client()
        # doc_ref = db.collection('jobs').document(job_id)
        # doc = await doc_ref.get()
        # if doc.exists:
        #     return Job(**doc.to_dict())
        return None
    
    async def _update_in_firestore(self, job: Job) -> None:
        """Update job in Firestore."""
        # TODO: Implement Firestore job update
        # from google.cloud import firestore
        # db = firestore.Client()
        # doc_ref = db.collection('jobs').document(job.job_id)
        # await doc_ref.update(job.dict())
        pass
    
    async def _delete_from_firestore(self, job_id: str) -> bool:
        """Delete job from Firestore."""
        # TODO: Implement Firestore job deletion
        # from google.cloud import firestore
        # db = firestore.Client()
        # doc_ref = db.collection('jobs').document(job_id)
        # await doc_ref.delete()
        # return True
        return False
    
    async def _get_by_user_from_firestore(self, user_id: str, limit: int, offset: int) -> List[Job]:
        """Get jobs by user from Firestore."""
        # TODO: Implement Firestore user jobs query
        # from google.cloud import firestore
        # db = firestore.Client()
        # query = db.collection('jobs').where('user_id', '==', user_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).offset(offset)
        # docs = await query.stream()
        # return [Job(**doc.to_dict()) for doc in docs]
        return []
    
    async def _cleanup_expired_from_firestore(self, expiry_date: datetime) -> int:
        """Clean up expired jobs from Firestore."""
        # TODO: Implement Firestore cleanup
        # from google.cloud import firestore
        # db = firestore.Client()
        # query = db.collection('jobs').where('created_at', '<', expiry_date)
        # docs = await query.stream()
        # count = 0
        # for doc in docs:
        #     await doc.reference.delete()
        #     count += 1
        # return count
        return 0
    
    async def list_jobs(self, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """List all jobs with pagination."""
        try:
            if self.settings.is_development():
                # In-memory pagination
                all_jobs = list(self._jobs_cache.values())
                
                # Sort by created_at descending
                all_jobs.sort(key=lambda x: x.created_at, reverse=True)
                
                # Apply pagination
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                jobs = all_jobs[start_idx:end_idx]
                
                total_jobs = len(all_jobs)
                total_pages = (total_jobs + page_size - 1) // page_size
                
                result = {
                    'jobs': jobs,
                    'total_jobs': total_jobs,
                    'total_pages': total_pages,
                    'current_page': page,
                    'page_size': page_size
                }
                
                logger.info(
                    "Listed jobs from cache",
                    total_jobs=total_jobs,
                    page=page,
                    page_size=page_size
                )
                
                return result
            
            else:
                # Firestore implementation would be here
                logger.info("Firestore job listing not implemented")
                return {
                    'jobs': [],
                    'total_jobs': 0,
                    'total_pages': 0,
                    'current_page': page,
                    'page_size': page_size
                }
            
        except Exception as e:
            logger.error(
                "Failed to list jobs",
                page=page,
                page_size=page_size,
                error=str(e)
            )
            raise JobRepositoryError(f"Failed to list jobs: {e}")
    
    async def update_started_at(self, job_id: str, started_at: datetime) -> bool:
        """Update job started_at timestamp."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                return False
            
            job.started_at = started_at
            job.updated_at = datetime.utcnow()
            await self.update(job)
            return True
            
        except Exception as e:
            logger.error("Failed to update started_at", job_id=job_id, error=str(e))
            return False
    
    async def update_completed_at(self, job_id: str, completed_at: datetime) -> bool:
        """Update job completed_at timestamp."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                return False
            
            job.completed_at = completed_at
            job.updated_at = datetime.utcnow()
            await self.update(job)
            return True
            
        except Exception as e:
            logger.error("Failed to update completed_at", job_id=job_id, error=str(e))
            return False
    
    async def update_error_message(self, job_id: str, error_message: str) -> bool:
        """Update job error message."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                return False
            
            job.error_message = error_message
            job.updated_at = datetime.utcnow()
            await self.update(job)
            return True
            
        except Exception as e:
            logger.error("Failed to update error message", job_id=job_id, error=str(e))
            return False
    
    async def update_output_files(self, job_id: str, output_files: List[Dict[str, Any]]) -> bool:
        """Update job output files."""
        try:
            job = await self.get_by_id(job_id)
            if not job:
                return False
            
            # Convert dict to JobOutputFile objects
            job.output_files = [JobOutputFile(**file_data) for file_data in output_files]
            job.updated_at = datetime.utcnow()
            await self.update(job)
            return True
            
        except Exception as e:
            logger.error("Failed to update output files", job_id=job_id, error=str(e))
            return False


@lru_cache()
def get_job_repository() -> JobRepository:
    """Get cached job repository instance."""
    return JobRepository()