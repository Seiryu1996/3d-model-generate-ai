"""
Base repository interfaces and abstract classes.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Generic, TypeVar
from datetime import datetime

import structlog

from ..models.base import JobStatus
from ..models.job import Job, JobSummary


logger = structlog.get_logger(__name__)

T = TypeVar('T')


class Repository(ABC, Generic[T]):
    """Base repository interface."""
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""
        pass
    
    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get an entity by ID."""
        pass
    
    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update an existing entity."""
        pass
    
    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """Delete an entity by ID."""
        pass
    
    @abstractmethod
    async def list(self, limit: int = 10, offset: int = 0, **filters) -> List[T]:
        """List entities with pagination and filtering."""
        pass
    
    @abstractmethod
    async def count(self, **filters) -> int:
        """Count entities with filtering."""
        pass


class JobRepositoryInterface(Repository[Job]):
    """Interface for job repository operations."""
    
    @abstractmethod
    async def get_by_user_id(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Job]:
        """Get jobs by user ID."""
        pass
    
    @abstractmethod
    async def get_by_status(self, status: JobStatus, limit: int = 10, offset: int = 0) -> List[Job]:
        """Get jobs by status."""
        pass
    
    @abstractmethod
    async def get_pending_jobs(self, limit: int = 10) -> List[Job]:
        """Get jobs that are pending processing."""
        pass
    
    @abstractmethod
    async def get_expired_jobs(self, before_date: datetime) -> List[Job]:
        """Get jobs that have expired."""
        pass
    
    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus, **kwargs) -> bool:
        """Update job status and related fields."""
        pass
    
    @abstractmethod
    async def update_progress(self, job_id: str, progress: float) -> bool:
        """Update job progress."""
        pass
    
    @abstractmethod
    async def get_user_job_summaries(self, user_id: str, limit: int = 10, offset: int = 0) -> List[JobSummary]:
        """Get job summaries for a user."""
        pass
    
    @abstractmethod
    async def cleanup_expired_jobs(self, before_date: datetime) -> int:
        """Clean up expired jobs and return count of cleaned jobs."""
        pass