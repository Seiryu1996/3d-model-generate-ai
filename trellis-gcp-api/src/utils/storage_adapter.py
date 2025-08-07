"""
Storage adapter for unified access to GCP and local storage services.

This module provides a unified interface for storage operations that automatically
switches between GCP Cloud Storage and local MinIO based on the environment.
"""
import os
import asyncio
from typing import Optional, Dict, Any, List, Protocol, runtime_checkable
from pathlib import Path
from functools import lru_cache
import tempfile

import structlog
from google.cloud import storage as gcp_storage
from google.cloud import tasks_v2
import redis.asyncio as redis

from .config import get_settings


logger = structlog.get_logger(__name__)


@runtime_checkable
class StorageInterface(Protocol):
    """Interface for storage operations."""
    
    async def upload_file(self, bucket_name: str, file_path: str, object_name: str) -> str:
        """Upload a file to storage."""
        ...
    
    async def upload_from_bytes(self, bucket_name: str, data: bytes, object_name: str, content_type: str = None) -> str:
        """Upload bytes to storage."""
        ...
    
    async def download_file(self, bucket_name: str, object_name: str, file_path: str) -> None:
        """Download a file from storage."""
        ...
    
    async def download_as_bytes(self, bucket_name: str, object_name: str) -> bytes:
        """Download file as bytes."""
        ...
    
    async def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """Delete a file from storage."""
        ...
    
    async def list_files(self, bucket_name: str, prefix: str = "") -> List[str]:
        """List files in storage."""
        ...
    
    async def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if file exists."""
        ...


@runtime_checkable
class TaskQueueInterface(Protocol):
    """Interface for task queue operations."""
    
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in the queue."""
        ...
    
    async def delete_task(self, queue_name: str, task_name: str) -> bool:
        """Delete a task from the queue."""
        ...


class GCPStorageAdapter:
    """GCP Cloud Storage adapter."""
    
    def __init__(self):
        self.client = gcp_storage.Client()
    
    async def upload_file(self, bucket_name: str, file_path: str, object_name: str) -> str:
        """Upload a file to GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_filename, file_path)
            
            url = f"gs://{bucket_name}/{object_name}"
            
            logger.info(
                "File uploaded to GCS",
                bucket=bucket_name,
                object_name=object_name,
                url=url
            )
            
            return url
            
        except Exception as e:
            logger.error(
                "Failed to upload file to GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def upload_from_bytes(self, bucket_name: str, data: bytes, object_name: str, content_type: str = None) -> str:
        """Upload bytes to GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            if content_type:
                blob.content_type = content_type
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_string, data)
            
            url = f"gs://{bucket_name}/{object_name}"
            
            logger.info(
                "Bytes uploaded to GCS",
                bucket=bucket_name,
                object_name=object_name,
                size_bytes=len(data),
                url=url
            )
            
            return url
            
        except Exception as e:
            logger.error(
                "Failed to upload bytes to GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def download_file(self, bucket_name: str, object_name: str, file_path: str) -> None:
        """Download a file from GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.download_to_filename, file_path)
            
            logger.info(
                "File downloaded from GCS",
                bucket=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            
        except Exception as e:
            logger.error(
                "Failed to download file from GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def download_as_bytes(self, bucket_name: str, object_name: str) -> bytes:
        """Download file as bytes from GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, blob.download_as_bytes)
            
            logger.info(
                "File downloaded as bytes from GCS",
                bucket=bucket_name,
                object_name=object_name,
                size_bytes=len(data)
            )
            
            return data
            
        except Exception as e:
            logger.error(
                "Failed to download bytes from GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """Delete a file from GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.delete)
            
            logger.info(
                "File deleted from GCS",
                bucket=bucket_name,
                object_name=object_name
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to delete file from GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            return False
    
    async def list_files(self, bucket_name: str, prefix: str = "") -> List[str]:
        """List files in GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            blobs = await loop.run_in_executor(None, list, bucket.list_blobs(prefix=prefix))
            
            file_names = [blob.name for blob in blobs]
            
            logger.info(
                "Files listed from GCS",
                bucket=bucket_name,
                prefix=prefix,
                count=len(file_names)
            )
            
            return file_names
            
        except Exception as e:
            logger.error(
                "Failed to list files from GCS",
                bucket=bucket_name,
                prefix=prefix,
                error=str(e)
            )
            return []
    
    async def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if file exists in GCP Cloud Storage."""
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(None, blob.exists)
            
            return exists
            
        except Exception as e:
            logger.error(
                "Failed to check file existence in GCS",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            return False


class LocalStorageAdapter:
    """Local MinIO storage adapter for development."""
    
    def __init__(self):
        self.settings = get_settings()
        # For simplicity, we'll use file system operations
        # In a real implementation, you'd use MinIO client
        self.base_path = Path("/tmp/trellis-storage")
        self.base_path.mkdir(exist_ok=True)
    
    def _get_file_path(self, bucket_name: str, object_name: str) -> Path:
        """Get local file path for bucket and object."""
        bucket_path = self.base_path / bucket_name
        bucket_path.mkdir(exist_ok=True)
        return bucket_path / object_name
    
    async def upload_file(self, bucket_name: str, file_path: str, object_name: str) -> str:
        """Upload a file to local storage."""
        try:
            source_path = Path(file_path)
            dest_path = self._get_file_path(bucket_name, object_name)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            import shutil
            shutil.copy2(source_path, dest_path)
            
            url = f"minio://{bucket_name}/{object_name}"
            
            logger.info(
                "File uploaded to local storage",
                bucket=bucket_name,
                object_name=object_name,
                url=url
            )
            
            return url
            
        except Exception as e:
            logger.error(
                "Failed to upload file to local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def upload_from_bytes(self, bucket_name: str, data: bytes, object_name: str, content_type: str = None) -> str:
        """Upload bytes to local storage."""
        try:
            dest_path = self._get_file_path(bucket_name, object_name)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            dest_path.write_bytes(data)
            
            url = f"minio://{bucket_name}/{object_name}"
            
            logger.info(
                "Bytes uploaded to local storage",
                bucket=bucket_name,
                object_name=object_name,
                size_bytes=len(data),
                url=url
            )
            
            return url
            
        except Exception as e:
            logger.error(
                "Failed to upload bytes to local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def download_file(self, bucket_name: str, object_name: str, file_path: str) -> None:
        """Download a file from local storage."""
        try:
            source_path = self._get_file_path(bucket_name, object_name)
            dest_path = Path(file_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            import shutil
            shutil.copy2(source_path, dest_path)
            
            logger.info(
                "File downloaded from local storage",
                bucket=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            
        except Exception as e:
            logger.error(
                "Failed to download file from local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def download_as_bytes(self, bucket_name: str, object_name: str) -> bytes:
        """Download file as bytes from local storage."""
        try:
            file_path = self._get_file_path(bucket_name, object_name)
            data = file_path.read_bytes()
            
            logger.info(
                "File downloaded as bytes from local storage",
                bucket=bucket_name,
                object_name=object_name,
                size_bytes=len(data)
            )
            
            return data
            
        except Exception as e:
            logger.error(
                "Failed to download bytes from local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            raise
    
    async def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._get_file_path(bucket_name, object_name)
            
            if file_path.exists():
                file_path.unlink()
                
                logger.info(
                    "File deleted from local storage",
                    bucket=bucket_name,
                    object_name=object_name
                )
                
                return True
            else:
                logger.warning(
                    "File not found for deletion",
                    bucket=bucket_name,
                    object_name=object_name
                )
                return False
                
        except Exception as e:
            logger.error(
                "Failed to delete file from local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            return False
    
    async def list_files(self, bucket_name: str, prefix: str = "") -> List[str]:
        """List files in local storage."""
        try:
            bucket_path = self.base_path / bucket_name
            
            if not bucket_path.exists():
                return []
            
            files = []
            for file_path in bucket_path.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(bucket_path)
                    if str(rel_path).startswith(prefix):
                        files.append(str(rel_path))
            
            logger.info(
                "Files listed from local storage",
                bucket=bucket_name,
                prefix=prefix,
                count=len(files)
            )
            
            return files
            
        except Exception as e:
            logger.error(
                "Failed to list files from local storage",
                bucket=bucket_name,
                prefix=prefix,
                error=str(e)
            )
            return []
    
    async def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if file exists in local storage."""
        try:
            file_path = self._get_file_path(bucket_name, object_name)
            return file_path.exists()
            
        except Exception as e:
            logger.error(
                "Failed to check file existence in local storage",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e)
            )
            return False


class GCPTaskQueueAdapter:
    """GCP Cloud Tasks adapter."""
    
    def __init__(self):
        self.client = tasks_v2.CloudTasksClient()
        self.settings = get_settings()
    
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in GCP Cloud Tasks."""
        try:
            import json
            from google.protobuf import timestamp_pb2
            import time
            
            # Create task
            task = {
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": f"{self.settings.API_BASE_URL}/api/v1/worker/process",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(payload).encode(),
                }
            }
            
            # Add delay if specified
            if delay_seconds > 0:
                timestamp = timestamp_pb2.Timestamp()
                timestamp.FromSeconds(int(time.time() + delay_seconds))
                task["schedule_time"] = timestamp
            
            # Create full queue path
            parent = self.client.queue_path(
                self.settings.GCP_PROJECT_ID,
                self.settings.GCP_LOCATION,
                queue_name
            )
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                self.client.create_task,
                request={"parent": parent, "task": task}
            )
            
            task_id = response.name.split("/")[-1]
            
            logger.info(
                "Task created in GCP Cloud Tasks",
                queue=queue_name,
                task_id=task_id,
                delay_seconds=delay_seconds
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to create task in GCP Cloud Tasks",
                queue=queue_name,
                error=str(e)
            )
            raise
    
    async def delete_task(self, queue_name: str, task_name: str) -> bool:
        """Delete a task from GCP Cloud Tasks."""
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.client.delete_task, name=task_name)
            
            logger.info(
                "Task deleted from GCP Cloud Tasks",
                queue=queue_name,
                task_name=task_name
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to delete task from GCP Cloud Tasks",
                queue=queue_name,
                task_name=task_name,
                error=str(e)
            )
            return False


class LocalTaskQueueAdapter:
    """Local Redis-based task queue adapter for development."""
    
    def __init__(self):
        self.settings = get_settings()
        self._redis_client = None
    
    async def _get_redis_client(self):
        """Get Redis client."""
        if self._redis_client is None:
            self._redis_client = redis.Redis(
                host=self.settings.REDIS_HOST,
                port=self.settings.REDIS_PORT,
                decode_responses=True
            )
        return self._redis_client
    
    async def create_task(self, queue_name: str, payload: Dict[str, Any], delay_seconds: int = 0) -> str:
        """Create a task in Redis queue."""
        try:
            import json
            import uuid
            import time
            
            redis_client = await self._get_redis_client()
            
            task_id = str(uuid.uuid4())
            task_data = {
                "id": task_id,
                "payload": payload,
                "created_at": time.time(),
                "scheduled_at": time.time() + delay_seconds
            }
            
            # Add to queue
            await redis_client.lpush(f"queue:{queue_name}", json.dumps(task_data))
            
            logger.info(
                "Task created in Redis queue",
                queue=queue_name,
                task_id=task_id,
                delay_seconds=delay_seconds
            )
            
            return task_id
            
        except Exception as e:
            logger.error(
                "Failed to create task in Redis queue",
                queue=queue_name,
                error=str(e)
            )
            raise
    
    async def delete_task(self, queue_name: str, task_name: str) -> bool:
        """Delete a task from Redis queue (not easily implemented)."""
        # This is difficult to implement efficiently in Redis
        # For now, just log and return True
        logger.info(
            "Task deletion requested (not implemented for Redis)",
            queue=queue_name,
            task_name=task_name
        )
        return True



async def health_check_local_services() -> Dict[str, str]:
    """Health check for local development services."""
    health_status = {}
    
    # For local development, assume services are healthy if containers are running
    # In a real implementation, you'd check MinIO, Redis, etc.
    health_status['storage'] = 'healthy'
    health_status['redis'] = 'healthy'
    
    return health_status


async def health_check_gcp_services() -> Dict[str, str]:
    """Health check for GCP services."""
    health_status = {}
    
    # Check Cloud Storage
    try:
        storage_client = gcp_storage.Client()
        # Try to list buckets as a health check
        list(storage_client.list_buckets(max_results=1))
        health_status['cloud_storage'] = 'healthy'
    except Exception as e:
        logger.warning("Cloud Storage health check failed", error=str(e))
        health_status['cloud_storage'] = 'unhealthy'
    
    # Check Cloud Tasks
    try:
        tasks_client = tasks_v2.CloudTasksClient()
        # Basic connectivity check
        health_status['cloud_tasks'] = 'healthy'
    except Exception as e:
        logger.warning("Cloud Tasks health check failed", error=str(e))
        health_status['cloud_tasks'] = 'unhealthy'
    
    return health_status

class StorageManager:
    """Unified storage manager that switches between GCP and local storage."""
    
    def __init__(self):
        self.settings = get_settings()
        self._storage = None
        self._task_queue = None
    
    @property
    def storage(self) -> StorageInterface:
        """Get storage adapter based on environment."""
        if self._storage is None:
            if self.settings.is_development():
                self._storage = LocalStorageAdapter()
                logger.info("Using local storage adapter")
            else:
                self._storage = GCPStorageAdapter()
                logger.info("Using GCP storage adapter")
        return self._storage
    
    @property
    def task_queue(self) -> TaskQueueInterface:
        """Get task queue adapter based on environment."""
        if self._task_queue is None:
            if self.settings.is_development():
                self._task_queue = LocalTaskQueueAdapter()
                logger.info("Using local task queue adapter")
            else:
                self._task_queue = GCPTaskQueueAdapter()
                logger.info("Using GCP task queue adapter")
        return self._task_queue
    
    async def health_check(self) -> Dict[str, str]:
        """Perform health check on all storage services."""
        if self.settings.is_development():
            return await health_check_local_services()
        else:
            return await health_check_gcp_services()
    
    def get_bucket_names(self) -> Dict[str, str]:
        """Get bucket names for different purposes."""
        if self.settings.is_development():
            return {
                'input': 'trellis-input-dev',
                'output': 'trellis-output-dev',
                'temp': 'trellis-temp-dev'
            }
        else:
            return {
                'input': self.settings.GCS_INPUT_BUCKET,
                'output': self.settings.GCS_OUTPUT_BUCKET,
                'temp': self.settings.GCS_TEMP_BUCKET
            }


@lru_cache()
def get_storage_manager() -> StorageManager:
    """Get cached storage manager instance."""
    return StorageManager()