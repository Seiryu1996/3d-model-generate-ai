"""
Services module for TRELLIS API.
"""

from .job_service import JobService, get_job_service
from .queue_service import QueueService, get_queue_service

__all__ = [
    'JobService',
    'get_job_service',
    'QueueService', 
    'get_queue_service'
]

# Lazy imports for worker-only services to avoid torch dependency in API
def get_trellis_service():
    """Get TRELLIS service (lazy import)."""
    from .trellis_service import get_trellis_service as _get_trellis_service
    return _get_trellis_service()

def get_worker_service():
    """Get worker service (lazy import)."""
    from .worker_service import get_worker_service as _get_worker_service
    return _get_worker_service()