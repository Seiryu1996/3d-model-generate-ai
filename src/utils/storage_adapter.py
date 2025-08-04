"""
Storage adapter that provides a unified interface for both GCP and local development.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from functools import lru_cache

import structlog

from .config import get_settings
from .gcp_clients import (
    get_storage_client as get_gcp_storage,
    get_firestore_client as get_gcp_firestore,
    get_tasks_client as get_gcp_tasks,
    health_check_gcp_services
)
from .local_storage import (
    get_local_storage_client,
    get_local_document_store,
    get_local_task_queue,
    health_check_local_services
)


logger = structlog.get_logger(__name__)


class StorageInterface(ABC):
    """Abstract interface for storage operations."""
    
    @abstractmethod
    async def upload_file(self, bucket_name: str, source_file: str, destination_name: str) -> str:
        """Upload a file to storage."""
        pass
    
    @abstractmethod
    async def upload_from_bytes(self, bucket_name: str, data: bytes, destination_name: str, content_type: str = None) -> str:
        """Upload data from bytes to storage."""
        pass
    
    @abstractmethod
    async def download_file(self, bucket_name: str, source_name: str, destination_file: str) -> None:
        """Download a file from storage."""
        pass
    
    @abstractmethod
    async def delete_file(self, bucket_name: str, file_name: str) -> None:
        """Delete a file from storage."""
        pass
    
    @abstractmethod
    async def generate_download_url(self, bucket_name: str, file_name: str, expiration_minutes: int = 60) -> str:
        """Generate a download URL for a file."""
        pass


class DocumentStoreInterface(ABC):
    """Abstract interface for document store operations."""
    
    @abstractmethod
    async def create_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Create a document."""
        pass
    
    @abstractmethod
    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document."""
        pass
    
    @abstractmethod
    async def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        """Update a document."""
        pass
    
    @abstractmethod
    async def delete_document(self, collection: str, document_id: str) -> None:
        """Delete a document."""
        pass


class TaskQueueInterface(ABC):
    """Abstract interface for task queue operations."""
    
    @abstractmethod
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in the queue."""
        pass


class GCPStorageAdapter(StorageInterface):
    """GCP Cloud Storage adapter."""
    
    def __init__(self):
        self.client = get_gcp_storage()
    
    async def upload_file(self, bucket_name: str, source_file: str, destination_name: str) -> str:
        return self.client.upload_file(bucket_name, source_file, destination_name)
    
    async def upload_from_bytes(self, bucket_name: str, data: bytes, destination_name: str, content_type: str = None) -> str:
        return self.client.upload_from_bytes(bucket_name, data, destination_name, content_type)
    
    async def download_file(self, bucket_name: str, source_name: str, destination_file: str) -> None:
        return self.client.download_file(bucket_name, source_name, destination_file)
    
    async def delete_file(self, bucket_name: str, file_name: str) -> None:
        return self.client.delete_file(bucket_name, file_name)
    
    async def generate_download_url(self, bucket_name: str, file_name: str, expiration_minutes: int = 60) -> str:
        return self.client.generate_signed_url(bucket_name, file_name, expiration_minutes)


class GCPDocumentStoreAdapter(DocumentStoreInterface):
    """GCP Firestore adapter."""
    
    def __init__(self):
        self.client = get_gcp_firestore()
    
    async def create_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        return self.client.create_document(collection, document_id, data)
    
    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        return self.client.get_document(collection, document_id)
    
    async def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        return self.client.update_document(collection, document_id, data)
    
    async def delete_document(self, collection: str, document_id: str) -> None:
        return self.client.delete_document(collection, document_id)


class GCPTaskQueueAdapter(TaskQueueInterface):
    """GCP Cloud Tasks adapter."""
    
    def __init__(self):
        self.client = get_gcp_tasks()
    
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        return self.client.create_task(queue_name, payload, delay_seconds)


class LocalStorageAdapter(StorageInterface):
    """Local MinIO storage adapter."""
    
    def __init__(self):
        self.client = get_local_storage_client()
    
    async def upload_file(self, bucket_name: str, source_file: str, destination_name: str) -> str:
        return self.client.upload_file(bucket_name, source_file, destination_name)
    
    async def upload_from_bytes(self, bucket_name: str, data: bytes, destination_name: str, content_type: str = None) -> str:
        return self.client.upload_from_bytes(bucket_name, data, destination_name, content_type)
    
    async def download_file(self, bucket_name: str, source_name: str, destination_file: str) -> None:
        return self.client.download_file(bucket_name, source_name, destination_file)
    
    async def delete_file(self, bucket_name: str, file_name: str) -> None:
        return self.client.delete_file(bucket_name, file_name)
    
    async def generate_download_url(self, bucket_name: str, file_name: str, expiration_minutes: int = 60) -> str:
        return self.client.generate_presigned_url(bucket_name, file_name, expiration_minutes)


class LocalDocumentStoreAdapter(DocumentStoreInterface):
    """Local SQLite document store adapter."""
    
    def __init__(self):
        self.client = get_local_document_store()
    
    async def create_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        return self.client.create_document(collection, document_id, data)
    
    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        return self.client.get_document(collection, document_id)
    
    async def update_document(self, collection: str, document_id: str, data: Dict[str, Any]) -> None:
        return self.client.update_document(collection, document_id, data)
    
    async def delete_document(self, collection: str, document_id: str) -> None:
        return self.client.delete_document(collection, document_id)


class LocalTaskQueueAdapter(TaskQueueInterface):
    """Local task queue adapter."""
    
    def __init__(self):
        self.client = get_local_task_queue()
    
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        return self.client.create_task(queue_name, payload, delay_seconds)


class StorageManager:
    """Storage manager that provides unified access to storage services."""
    
    def __init__(self):
        self.settings = get_settings()
        self._storage: Optional[StorageInterface] = None
        self._document_store: Optional[DocumentStoreInterface] = None
        self._task_queue: Optional[TaskQueueInterface] = None
    
    @property
    def storage(self) -> StorageInterface:
        """Get storage interface."""
        if self._storage is None:
            if self.settings.is_development():
                self._storage = LocalStorageAdapter()
                logger.info("Using local storage adapter (MinIO)")
            else:
                self._storage = GCPStorageAdapter()
                logger.info("Using GCP Cloud Storage adapter")
        return self._storage
    
    @property
    def document_store(self) -> DocumentStoreInterface:
        """Get document store interface."""
        if self._document_store is None:
            if self.settings.is_development():
                self._document_store = LocalDocumentStoreAdapter()
                logger.info("Using local document store adapter (SQLite)")
            else:
                self._document_store = GCPDocumentStoreAdapter()
                logger.info("Using GCP Firestore adapter")
        return self._document_store
    
    @property
    def task_queue(self) -> TaskQueueInterface:
        """Get task queue interface."""
        if self._task_queue is None:
            if self.settings.is_development():
                self._task_queue = LocalTaskQueueAdapter()
                logger.info("Using local task queue adapter")
            else:
                self._task_queue = GCPTaskQueueAdapter()
                logger.info("Using GCP Cloud Tasks adapter")
        return self._task_queue
    
    async def health_check(self) -> Dict[str, str]:
        """Perform health check on all storage services."""
        if self.settings.is_development():
            return await health_check_local_services()
        else:
            return await health_check_gcp_services()
    
    def get_bucket_names(self) -> Dict[str, str]:
        """Get bucket names for different purposes."""
        return {
            'models': self.settings.GCS_BUCKET_MODELS,
            'input': self.settings.GCS_BUCKET_INPUT,
            'output': self.settings.GCS_BUCKET_OUTPUT,
            'temp': self.settings.GCS_BUCKET_TEMP
        }


@lru_cache()
def get_storage_manager() -> StorageManager:
    """Get cached storage manager instance."""
    return StorageManager()